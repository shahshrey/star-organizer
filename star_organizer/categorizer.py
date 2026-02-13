import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Set

import structlog
from langchain.chat_models import init_chat_model

from star_organizer.models import (
    BATCH_SAVE_INTERVAL,
    MAX_CATEGORIZATION_RETRIES,
    MAX_GITHUB_LISTS,
    MAX_TOPICS_TO_INCLUDE,
    OPENAI_API_KEY,
    PARALLEL_CATEGORIZATION_WORKERS,
    RETRY_DELAY_SECONDS,
    AllCategories,
    OrganizedStarLists,
    RepoMetadata,
    StarListAssignment,
)

LOGGER = structlog.get_logger()


def _init_model(schema: Any) -> Any:
    model = init_chat_model(
        model="gpt-4.1-2025-04-14",
        model_provider="openai",
        api_key=OPENAI_API_KEY,
        temperature=0,
    )
    return model.with_structured_output(schema)


def _sanitize_name(raw: str) -> str:
    clean = raw.strip().upper().replace(" ", "_").replace("-", "_")
    return "".join(c for c in clean if c.isalnum() or c == "_")


def _build_context(meta: RepoMetadata) -> str:
    parts = [f"Repository: {meta.get('url', '')}"]
    if meta.get("name"):
        parts.append(f"Name: {meta['name']}")
    if meta.get("description"):
        parts.append(f"Description: {meta['description']}")
    if meta.get("topics"):
        parts.append(f"Topics/Tags: {', '.join(meta['topics'][:MAX_TOPICS_TO_INCLUDE])}")
    if meta.get("readme"):
        parts.append(f"\nREADME Preview:\n{meta['readme'][:500]}")
    return "\n".join(parts)


def _build_existing_lists_section(existing_star_lists: Dict[str, str]) -> str:
    if not existing_star_lists:
        return "\n\nNo existing lists yet - you will create the first one.\n"

    lists_count = len(existing_star_lists)

    section_lines = [
        "\n\n=== PREDEFINED CATEGORIES ===",
        f"⚠️ CRITICAL: These {lists_count} categories were created by analyzing ALL repositories.",
        "⚠️ YOU MUST choose ONE of these categories - DO NOT create new ones.",
        "⚠️ Pick the BEST FIT from the list below:\n"
    ]

    for list_name, list_description in sorted(existing_star_lists.items()):
        section_lines.append(f""" 
        <CATEGORY>
        
        <NAME>
        {list_name}
        </NAME> 
        
        <DESCRIPTION>
        {list_description}
        </DESCRIPTION>
        
        </CATEGORY> 
        """)

    section_lines.append(f"\n⚠️ Total categories: {lists_count}/{MAX_GITHUB_LISTS} (ALL SLOTS USED - GitHub limit)")
    section_lines.append("⚠️ You MUST select ONE of the above categories. Creating new categories is NOT ALLOWED.\n")
    return "\n".join(section_lines)


def create_categories(repos_metadata: List[RepoMetadata]) -> Dict[str, str]:
    LOGGER.info("creating_categories", total_repos=len(repos_metadata))

    repos_formatted = []
    for i, repo in enumerate(repos_metadata, 1):
        lines = [
            f"=== Repository #{i} ===",
            f"URL: {repo['url']}"
        ]
        if repo.get('name'):
            lines.append(f"Name: {repo['name']}")
        if repo.get('description'):
            desc = repo['description'][:300]
            lines.append(f"Description: {desc}")
        if repo.get('topics') and len(repo['topics']) > 0:
            topics_str = ', '.join(repo['topics'][:15])
            lines.append(f"Topics: {topics_str}")
        if repo.get('readme'):
            readme_preview = repo['readme'][:500].replace('\n', ' ').strip()
            lines.append(f"README Preview: {readme_preview}...")
        lines.append("=" * 50)
        repos_formatted.append('\n'.join(lines))

    repos_context = '\n\n'.join(repos_formatted)

    prompt = f"""
    You are an expert at organizing GitHub Stars into meaningful, technology-specific lists.
    
    TASK: Analyze ALL {len(repos_metadata)} repositories below and create EXACTLY 32 categories that will organize them effectively.
    
    <REPOSITORIES WITH METADATA>
    {repos_context}
    </REPOSITORIES WITH METADATA>
    
    ORGANIZATION PRINCIPLES:
    
    1. ⚠️ EXACTLY 32 CATEGORIES (GitHub's hard limit)
    - You MUST create exactly 32 categories - no more, no less
    - These categories should cover ALL the repositories in the list
    - Balance breadth and specificity to fit everything within 32 categories
    - Use the NAME, DESC, TOPICS, and README metadata to understand each repo
    
    2. BE TECHNOLOGY-SPECIFIC BUT NOT TOO NARROW
    - Include primary technology/language in category names (infer from NAME, DESC, TOPICS, and README)
    - Examples: PYTHON_LINTERS, REACT_COMPONENTS, AI_IMAGE_GENERATION
    - Only use generic names if tool is truly cross-platform
    - Balance specificity with the 32-category limit
    
    3. USE PREFIXES FOR ORGANIZATION
    - Language prefix: PYTHON_*, JAVASCRIPT_*, RUST_*, GO_*
    - Framework prefix: REACT_*, NEXTJS_*, DJANGO_*
    - Domain prefix: AI_*, MCP_*, WEB_*
    - Tool-specific prefix: CURSOR_*, CLAUDECODE_*
    
    4. REFERENCE MATERIALS ARE SEPARATE
    - AI Coding Assistant Prompts and Rules → AI_CODING_ASSISTANTS_PROMPTS_AND_RULES
    - Tutorials, courses, guides → LEARNING_RESOURCES
    - Interview prep → INTERVIEW_PREP
    - Awesome lists → categorize by domain (AI_AWESOME_LISTS, PYTHON_AWESOME_LISTS, etc.)
    
    5. DISTINGUISH APPLICATIONS FROM FRAMEWORKS
    - FRAMEWORKS/LIBRARIES: Code developers use to BUILD apps (suffix: _FRAMEWORKS)
    - APPLICATIONS/TOOLS: Complete ready-to-use software (AI_DESKTOP_APPLICATIONS, AI_EMAIL_TOOLS)
    
    6. PLATFORM VS FRAMEWORK
    - Only use platform-specific (iOS_*, ANDROID_*, MACOS_*) if EXCLUSIVELY for that platform
    - Cross-platform frameworks ≠ platform-specific
    
    7. CREATE BROAD CATEGORIES STRATEGICALLY
    - Look at the distribution of repos across different domains
    - Use NAME, DESC, TOPICS, and README to understand what each repo does
    - Group similar tools together (e.g., all file management tools, all system utilities)
    - Ensure every repo can fit into at least one category
    
    8. COMMON CATEGORY SUGGESTIONS (adjust based on actual repos):
    - AI_CODING_ASSISTANTS_TOOLS
    - AI_CODING_ASSISTANTS_PROMPTS_AND_RULES
    - AI_AGENTS_FRAMEWORKS
    - AI_IMAGE_GENERATION
    - AI_TRANSCRIPTION_TOOLS
    - AI_DESKTOP_APPLICATIONS
    - AI_AWESOME_LISTS
    - LEARNING_RESOURCES
    - INTERVIEW_PREP
    - PYTHON_LINTERS
    - PYTHON_COMMAND_LINE_TOOLS
    - PYTHON_DEPENDENCY_MANAGEMENT
    - NEXTJS_STARTER_KITS
    - REACT_COMPONENTS
    - DEVELOPER_TOOLS
    - SYSTEM_UTILITIES
    - FILE_MANAGEMENT_TOOLS
    - MACOS_SYSTEM_TOOLS
    - ANDROID_MODDING_TOOLS
    - WEB_FRAMEWORKS
    - SECURITY_SCANNING_TOOLS
    - etc.
    
    CRITICAL RULES:
    ⚠️ EXACTLY 32 categories - count them carefully
    ⚠️ Category names in UPPERCASE_WITH_UNDERSCORES
    ⚠️ Each category should be broad enough to include multiple repos
    ⚠️ Use NAME, DESC, TOPICS, and README to understand each repository's purpose
    ⚠️ Technology-specific names when appropriate (infer from NAME, DESC, TOPICS, and README)
    ⚠️ Cover the full spectrum of repos in the list
    ⚠️ Each description should be 1-2 sentences explaining what repos in that category help you do
    
    Return EXACTLY 32 categories that will organize all {len(repos_metadata)} repositories effectively.
    """

    llm = _init_model(AllCategories)
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            all_categories = llm.invoke(prompt)
            categories_dict = {cat.name: cat.description for cat in all_categories.categories}
            count = len(categories_dict)
            LOGGER.info('categories_generated', count=count, attempt=attempt)

            if count <= MAX_GITHUB_LISTS:
                for cat_name, cat_desc in sorted(categories_dict.items()):
                    LOGGER.info('category_defined', name=cat_name, description=cat_desc)
                return categories_dict

            LOGGER.warning('too_many_categories', count=count, max=MAX_GITHUB_LISTS, attempt=attempt)
            if attempt < max_attempts:
                time.sleep(RETRY_DELAY_SECONDS)
        except Exception as e:
            LOGGER.error('category_creation_failed', error=str(e), attempt=attempt)
            if attempt >= max_attempts:
                raise
            time.sleep(RETRY_DELAY_SECONDS)

    LOGGER.warning('using_last_attempt_categories', count=len(categories_dict), trimming_to=MAX_GITHUB_LISTS)
    trimmed = dict(list(categories_dict.items())[:MAX_GITHUB_LISTS])
    return trimmed


def _build_assignment_prompt(repository_url: str, repository_context: str, existing_star_lists: Dict[str, str]) -> str:
    existing_lists_section = _build_existing_lists_section(existing_star_lists)

    return f"""
        You are an expert at organizing GitHub Stars into meaningful, technology-specific lists.

        STARRED REPOSITORY:
        URL: {repository_url}

        REPOSITORY DETAILS:

        <REPOSITORY CONTEXT>
        {repository_context}
        </REPOSITORY CONTEXT>

        <EXISTING LISTS>
        {existing_lists_section}
        </EXISTING LISTS>

        ORGANIZATION PRINCIPLES:

        0. ⚠️ PREDEFINED CATEGORIES ONLY
        - All 32 categories were created by analyzing ALL repositories in advance
        - You MUST select ONE of the existing categories listed above
        - DO NOT create new categories - this is CRITICAL
        - Pick the BEST FIT from the available categories
        - If multiple categories could fit, choose the most specific one
        - If no perfect fit exists, choose the closest match

        1. ONLY USE PROVIDED INFORMATION
        - Base decisions on: description, topics, language, README content
        - Do NOT guess, infer, or hallucinate capabilities
        - When in doubt, use broader categories
        - If something is not clear, put them in UNCATEGORIZED
        - You can create nested lists using breadcrumb notation: PYTHON_LINTERS/PYRIGHT (not PYRIGHT_LINTERS)

        2. BE TECHNOLOGY-SPECIFIC (BUT NOT TOO NARROW)
        - Include the primary technology/language in the list name
        - Examples: PYTHON_LINTERS (not LINTERS), REACT_COMPONENTS (not COMPONENTS)
        - Only use generic names if the tool is truly cross-platform and not tied to specific tech
        - Balance specificity with the 32-list limit: prefer broader useful categories over hyper-specific ones

        3. USE PREFIXES FOR ORGANIZATION
        - Language prefix: PYTHON_*, JAVASCRIPT_*, RUST_*, GO_*
        - Framework prefix: REACT_*, NEXTJS_*, DJANGO_*
        - Domain prefix: AI_*, MCP_*, WEB_*
        - Tool-specific prefix: CURSOR_*, CLAUDECODE_*
        - Think of prefixes as folders for grouping related repos
        - AI coding assistant prompts and rules have their own category: AI_CODING_ASSISTANTS_PROMPTS_AND_RULES

        4. REFERENCE MATERIALS ARE SEPARATE
        - AI Coding Assistant Prompts and Rules → AI_CODING_ASSISTANTS_PROMPTS_AND_RULES
          * Examples: Cursor rules, Claude prompts, Cline prompts, AI assistant configurations
          * These should NEVER be categorized as awesome lists or learning resources
          * Focus on the use case: helping developers work with AI coding assistants
          * Agentic coding tools should be categorized under AI_CODING_ASSISTANTS_TOOLS
        - Tutorials, courses, guides, roadmaps → LEARNING_RESOURCES
        - Interview prep materials → INTERVIEW_PREP
        - These are references, not tools

        5. PLATFORM VS FRAMEWORK
        - Use framework names when explicit (REACT_NATIVE_*, FLUTTER_*)
        - Only use platform-specific names (iOS_*, ANDROID_*, MACOS_*, WINDOWS_*) if the repo EXPLICITLY and ONLY targets that platform
        - iOS_* requires: Swift/Objective-C, Xcode, or iOS SDK mentions AND no cross-platform support
        - ANDROID_* requires: Kotlin/Java, Android SDK, or Gradle mentions AND no cross-platform support
        - MACOS_* requires: macOS-only APIs, Swift/Objective-C, or macOS-exclusive features AND no cross-platform support
        - Cross-platform frameworks ≠ platform-specific (if it runs on multiple OS, don't use platform-specific category)
        - Check README for "cross-platform", "multi-platform", "Windows, macOS, Linux" mentions

        6. DISTINGUISH APPLICATIONS FROM FRAMEWORKS
        - FRAMEWORKS/LIBRARIES: Code that developers use to BUILD other applications
          * Examples: React, FastAPI, LangChain, Prisma
          * Keywords: "framework", "library", "SDK", "API", "package", "module"
          * Purpose: Imported/integrated into other projects
        - APPLICATIONS/TOOLS: Complete, ready-to-use software
          * Examples: VS Code, Slack, Notion, Discord
          * Keywords: "app", "application", "software", "desktop app", "mobile app", "web app"
          * Purpose: Used directly by end users
        - If it's an APPLICATION, create domain-specific category: AI_DESKTOP_APPLICATIONS, AI_EMAIL_TOOLS, etc.
        - If it's a FRAMEWORK, use *_FRAMEWORKS suffix: AI_AGENTS_FRAMEWORKS, WEB_FRAMEWORKS, etc.

        7. AWESOME LISTS: CATEGORIZE BY DOMAIN, NOT FORMAT
        - ⚠️ CRITICAL: "Awesome lists" should be categorized by their PRIMARY DOMAIN/TOPIC
        - ✅ CORRECT: awesome-ai → AI_AWESOME_LISTS
        - ✅ CORRECT: awesome-python → PYTHON_AWESOME_LISTS  
        - ✅ CORRECT: awesome-react → REACT_AWESOME_LISTS
        - ✅ CORRECT: awesome-zsh-plugins → SHELL_AWESOME_LISTS or LEARNING_RESOURCES
        - ✅ CORRECT: awesome-tunneling → NETWORKING_AWESOME_LISTS or LEARNING_RESOURCES
        - ❌ WRONG: awesome-zsh-plugins → AI_AWESOME_LISTS (ZSH is NOT AI-related!)
        - ❌ WRONG: awesome-tunneling → AI_AWESOME_LISTS (Tunneling is NOT AI-related!)
        - Read the awesome list's content/topic, then categorize by that domain

        8. BALANCE SPECIFICITY WITH THE 32-LIST LIMIT
        - Prefer specific categories when possible, but consider the list count
        - Examples of good specific categories (when space available):
          * PDF tools → PDF_MANIPULATION_TOOLS or DOCUMENT_PROCESSING_TOOLS
          * File managers → FILE_MANAGERS or WEB_FILE_MANAGERS
          * Download managers → DOWNLOAD_MANAGERS
          * Backup tools → BACKUP_TOOLS or ANDROID_BACKUP_TOOLS
          * System monitors → SYSTEM_MONITORS or PERFORMANCE_MONITORING_TOOLS
          * File transfer tools → FILE_TRANSFER_TOOLS
        - When approaching the 32-list limit (25+ lists), consolidate into broader categories:
          * Multiple specific AI tools → AI_DESKTOP_APPLICATIONS
          * Multiple system utilities → SYSTEM_UTILITIES or DEVELOPER_TOOLS
          * Multiple file tools → FILE_MANAGEMENT_TOOLS
        - Ask yourself: "What SPECIFIC problem does this solve?" Then balance specificity with list count

        9. PREFER EXISTING LISTS WHEN APPROPRIATE
        - Read existing list descriptions carefully
        - If a repo could reasonably fit an existing list, USE IT
        - Only create new lists when there's a clear gap
        - Avoid proliferation of similar lists

        10. BE SPECIFIC ABOUT PURPOSE
        - Identify the PRIMARY use case from the signals provided
        - Use specific names that clearly indicate what belongs in the list
        - Examples: AI_IMAGE_GENERATION, PYTHON_TESTING, SECURITY_SCANNING, FILE_TRANSFER_TOOLS, PDF_MANIPULATION_TOOLS
        - The category name should immediately tell someone what the repos DO

        CRITICAL RULES - READ CAREFULLY:
        ⚠️ MUST USE PREDEFINED CATEGORIES - All 32 categories are predefined, choose the best fit
        ⚠️ DO NOT CREATE NEW CATEGORIES - This will cause errors
        ⚠️ ONLY use information provided - do not hallucinate
        ⚠️ Pick the MOST SPECIFIC category that fits, or the closest match if no perfect fit
        ⚠️ The category name you return MUST EXACTLY MATCH one from the list above
        ⚠️ ONE primary purpose only - choose one category

        Return:
        1. A list name (UPPERCASE with underscores)
        2. A clear 1-2 sentence description of what repos in this list help you do
        3. A clear, concise 1-2 sentence description of what THIS SPECIFIC repository does and its key features
        4. A brief explanation of WHY this repository belongs in this category (cite specific features, technologies, or purposes from the provided context)
        """


def categorize_repos(
    repos_metadata: List[RepoMetadata],
    organized: OrganizedStarLists,
    save_fn,
    save_path: str,
) -> int:
    LOGGER.info("starting_categorization", repos=len(repos_metadata), workers=PARALLEL_CATEGORIZATION_WORKERS)

    categorized_count = 0
    lock = threading.Lock()
    list_descriptions = {name: data["description"] for name, data in organized.items()}
    thread_local = threading.local()

    def get_model():
        if not hasattr(thread_local, "model"):
            thread_local.model = _init_model(StarListAssignment)
        return thread_local.model

    def process_repo(idx: int, meta: RepoMetadata):
        url = meta.get("url", "")
        if not url:
            return None

        LOGGER.info(
            "processing_repository",
            index=idx,
            total=len(repos_metadata),
            repository=meta.get("name", ""),
            url=url,
        )

        context = _build_context(meta)
        fallback = StarListAssignment(
            name="DEVELOPER_TOOLS",
            description="Development tools and utilities",
            repo_description="A development tool or utility for software development",
            reasoning="Fallback categorization due to processing error",
        )

        for attempt in range(MAX_CATEGORIZATION_RETRIES):
            try:
                prompt = _build_assignment_prompt(url, context, list_descriptions)
                assignment = get_model().invoke(prompt)
                assignment.name = _sanitize_name(assignment.name)
                if assignment.name and assignment.name != "UNCATEGORIZED":
                    return (url, meta.get("name", ""), assignment)
                if attempt < MAX_CATEGORIZATION_RETRIES - 1:
                    LOGGER.warning("invalid_list_name_retrying", url=url, attempt=attempt + 1)
                    time.sleep(RETRY_DELAY_SECONDS)
            except Exception as e:
                LOGGER.warning("categorization_failed_retrying", url=url, attempt=attempt + 1, error=str(e))
                if attempt < MAX_CATEGORIZATION_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)

        LOGGER.error("categorization_failed_using_fallback", url=url)
        return (url, meta.get("name", ""), fallback)

    with ThreadPoolExecutor(max_workers=PARALLEL_CATEGORIZATION_WORKERS) as executor:
        future_map = {
            executor.submit(process_repo, i + 1, meta): (i + 1, meta)
            for i, meta in enumerate(repos_metadata)
        }
        for future in as_completed(future_map):
            try:
                result = future.result()
            except Exception as e:
                idx, meta = future_map[future]
                LOGGER.error("categorization_worker_failed", index=idx, error=str(e))
                continue

            if result is None:
                continue

            url, repo_name, assignment = result

            with lock:
                target = assignment.name
                if target not in organized:
                    LOGGER.warning("category_not_in_predefined_list_using_fallback",
                                  attempted_list=target,
                                  available_categories=', '.join(sorted(organized.keys())))
                    target = "DEVELOPER_TOOLS"
                    if target not in organized:
                        available = list(organized.keys())
                        if available:
                            target = available[0]
                            LOGGER.warning("developer_tools_not_found_using_first_category", fallback=target)
                        else:
                            continue

                organized[target]["repos"].append({
                    "url": url,
                    "description": assignment.repo_description,
                    "reasoning": assignment.reasoning,
                })
                categorized_count += 1

                LOGGER.info(
                    "repository_categorized",
                    repository=repo_name,
                    assigned_to_list=target,
                    list_description=assignment.description,
                    created_new_list=False,
                )

                if categorized_count % BATCH_SAVE_INTERVAL == 0:
                    save_fn(save_path, organized)
                    LOGGER.info("progress_checkpoint_saved", categorized_so_far=categorized_count)

    save_fn(save_path, organized)
    return categorized_count
