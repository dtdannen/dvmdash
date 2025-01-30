from github import Github
from datetime import datetime


def get_sorted_issues(repo_name, state="all"):
    g = Github()

    try:
        repo = g.get_repo(repo_name)
        issues = repo.get_issues(state=state)
        issues_list = list(issues)
        issues_list.sort(key=lambda x: x.created_at, reverse=True)
        return issues_list

    except Exception as e:
        print(f"Error: {e}")
        return None


def print_issues(issues):
    if not issues:
        print("No issues found or error occurred")
        return

    for issue in issues:
        created_date = issue.created_at.strftime("%Y-%m-%d")
        status = "🟢 Open" if issue.state == "open" else "🔴 Closed"

        # Check for associated PRs
        has_pr = issue.pull_request is not None
        pr_indicator = "🔗 Has PR" if has_pr else "❌ No PR"

        # If there's an associated PR, get its URL and extract the number
        pr_details = ""
        if has_pr:
            pr_url = issue.pull_request.html_url
            pr_number = pr_url.split("/")[-1]
            pr_details = f" (PR: #{pr_number})"

        print(
            f"[{created_date}] {status} - {pr_indicator} - Issue #{issue.number}: {issue.title}{pr_details}"
        )


def get_open_issues_count_without_PRs(repo_name):
    issues = get_sorted_issues(repo_name, state="open")
    open_issues_without_prs = [issue for issue in issues if issue.pull_request is None]
    return open_issues_without_prs


if __name__ == "__main__":
    repo_name = "dtdannen/dvmdash"
    issues = get_sorted_issues(repo_name)
    print_issues(issues)

    # print all open issues without PRs
    open_issues_without_prs = get_open_issues_count_without_PRs(repo_name)
    for issue in open_issues_without_prs:
        print(issue)
