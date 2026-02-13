import os
from typing import Any, Dict, List, TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

OUTPUT_FILE = "organized_stars.json"
SYNC_STATE_FILE = ".sync_to_github_state.json"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

README_LINES_TO_FETCH = 150
GITHUB_API_TIMEOUT_SECONDS = 10
MAX_TOPICS_TO_INCLUDE = 50
MAX_GITHUB_LISTS = 32
MAX_CATEGORIZATION_RETRIES = 3
RETRY_DELAY_SECONDS = 2

GH_TIMEOUT = 30
RATE_LIMIT_LIST = 0.3
RATE_LIMIT_ITEM = 0.3
MAX_SYNC_WORKERS = 8
LIST_MAX_WORKERS = 8
CREATE_BATCH_SIZE = 15
REPO_LOOKUP_BATCH_SIZE = 40
ADD_BATCH_SIZE = 10
MAX_GQL_RETRIES = 5
RETRY_BACKOFF_BASE = 2.0
GITHUB_ERROR_RETRY_DELAY = 3.0
PROGRESS_INTERVAL = 20

PARALLEL_METADATA_WORKERS = 15
PARALLEL_CATEGORIZATION_WORKERS = 100
BATCH_SAVE_INTERVAL = 20


class CategoryNameAndDescription(BaseModel):
    name: str = Field(description="The name of the category")
    description: str = Field(
        description="A concise 1-2 sentence description of what repos in this category help you do"
    )


class AllCategories(BaseModel):
    categories: List[CategoryNameAndDescription] = Field(
        description="A list of exactly 32 categories and their descriptions"
    )


class StarListAssignment(BaseModel):
    name: str = Field(description="The name of the list to assign the star to")
    description: str = Field(
        description="A concise 1-2 sentence description of what repos in this list help you do"
    )
    repo_description: str = Field(
        description="A clear, concise 1-2 sentence description of what this specific repository does and its key features"
    )
    reasoning: str = Field(
        description="A brief explanation of why this repository was assigned to this specific list/category"
    )


class RepoMetadata(TypedDict):
    url: str
    name: str
    full_name: str
    description: str
    topics: List[str]
    readme: str


OrganizedStarLists = Dict[str, Dict[str, Any]]
