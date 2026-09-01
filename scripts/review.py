from wsgiref import headers

from google import genai
from pydantic import BaseModel, Field  # type: ignore[import-not-found]
from typing import List, Literal
import os
import requests

class Issue(BaseModel):
    file: str = Field(..., description="The file path where the issue occurs.")
    description: str = Field(description= "What the issue is and why it matters.")
    severity: Literal["low", "medium", "high"] = Field(description="How serious the issue is.")

class PRReviewRequest(BaseModel):
    summary: str = Field(description="1-2 sentence overview of the PR's changes.")
    issues: List[Issue] = Field(description="Specific problems found if any.")
    suggestions:List[str] = Field(description="General improvement suggestions, non-bloking.")
    approve: bool = Field(description="Whether this PR looks safe to merge as -is")

def build_prompt(diff: str) -> str:
    """Build the review prompt to send as the model's input"""
    return f"""You are reviewing a pull request. Analyze the diff below and idenitfy:
    - Bugs or logic errors
    - Unclear or hand-to-maintain code
    - Missing edge case handling

    Be specific and reference the file names where relevant. Keep the summary brief.
    If the PR looks clean, it's fine to return an empty issues list.

    Diff:
    {diff}
    """

def get_pr_diff(repo: str, pr_number: str, github_token: str) -> str:
    """ Fetch the PR's diff from GitHub API"""
    url = f"https://api.github.com/repos/{repo}/pulls{pr_number}"
    headers = {
        "Authorization": f"Bearer (github_token)",
        "Accept": "application/vnd.github.diff",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def review_diff(diff: str, api_key: str) -> PRReview:
    """Send the MR diff to Gemini and get back review feedback."""

    interaction = client.interactions.create(
        model="gemini-3.7-flash",
        input=build_prompt(diff),
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": PRReview.model_json_schema()
        }
    )

    response = PRReview.model_validate_json(interaction.output_text)
    return response

def format_review(review: PRReview) -> str:
    """ Convert a PRReview Object into a markdown comment string """
    lines = [f"### PR Review \n", f"(review.summary)\n"]

    if review.issues:
        lines.append("**Issues Found: **.\n")

        for issues in review.issues:
            lines.append(f"- **[{issue.severity.upper()}]** `{issue.file}`: {issue.description}")
            lines.append(f"  - **Description:** {issues.description}\n")
            lines.append(f"  - **Severity:** {issues.severity}\n")

    else:
        lines.append("No issues found.")

    if review.suggestions:
        lines.append("**Suggestions: **.\n")

        for suggestion in review.suggestions:
            lines.append(f"- {suggestion}\n")
        lines.append("\n")
    

    verdict = "Looks good to merge!" if review.approve else "Needs changes before merging"
    lines.append(f"\n{verdict}")

    return "\n".join(lines)

def post_comment(repo: str, pr_number: str, comment: str, github_token: str):
    """Post the review as a comment on the PR """
    url = f"https://api.github.com/repos/{repo}/pulls{pr_number}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.diff",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    response = requests.post(url, headers=headers, json={"body": comment})
    response.raise_for_status()

def main():
    """ Orchestrates the four steps above using env vars from the workflow"""
    repo = os.environ["REPO"]
    pr_number = os.environ["PR_NUMBER"]
    github_token = os.environ["GITHUB_TOKEN"]
    api_key = os.environ["GENAI_API_KEY"]

    diff = get_pr_diff(repo, pr_number, github_token)
    review = review_diff(diff, api_key)
    review_format = format_review(review_object)
    post_comment(repo, pr_number, review_format, github_token)

if __name__ == "__main__":
    main()