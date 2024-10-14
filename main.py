import aiohttp
import asyncio
import async_timeout
import base64
import os
import re
import time
import logging

# 设置日志配置
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# 创建文件处理器
file_handler = logging.FileHandler(
    "github_repos.log", mode="w", encoding="utf-8"
)  # 确保以utf-8编码保存
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


GITHUB_TOKEN = ""  # 需要替换为你的 GitHub Token
USERNAME = ""  # 需要替换为待检查的 GitHub 用户名
CAUTION_STATEMENT_CN = """
# 免责声明

> [!CAUTION]  
> 本分支仅用于个人开发提供学习研究，请勿直接使用任何附件。如出现任何有关源附件问题，本作者概不负责。

---
"""

CAUTION_STATEMENT_EN = """
> [!CAUTION]  
> This branch is only for personal development, study and research. Please do not use any attachments directly. The author is not responsible for any problems with the source attachments.
"""

CAUTION_BLOCK_PATTERN = r"(# 免责声明.*?---\s*)|(\> \[!CAUTION\].*?---\s*)"  # regex pattern to match CAUTION blocks


async def fetch_repositories(session):
    url_template = f"https://api.github.com/users/{USERNAME}/repos?page={{}}"
    repos = []
    page = 1
    while True:
        url = url_template.format(page)
        async with session.get(
            url, headers={"Authorization": f"token {GITHUB_TOKEN}"}
        ) as response:
            if response.status == 200:
                data = await response.json()
                if not data:
                    break
                repos.extend(data)
                logging.info(f"成功获取第 {page} 页：{len(data)} 个仓库")
                page += 1
            else:
                logging.info(f"获取仓库失败：{response.status}")
                return []
    logging.info(f"总共获取的仓库数量：{len(repos)}")
    return repos


async def fetch_readme(session, repo_name, branch):
    url = f"https://raw.githubusercontent.com/{USERNAME}/{repo_name}/{branch}/README.md"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.text()
            else:
                logging.info(f"仓库 {repo_name} 的 README.md 不存在：{response.status}")
    except Exception as e:
        logging.info(f"获取 {repo_name} 的 README.md 时出错：{e}")
    return None


async def create_readme(session, repo_name, content, branch):
    url = f"https://api.github.com/repos/{USERNAME}/{repo_name}/contents/README.md"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

    data = {
        "message": "创建 README.md 并添加免责声明",
        "content": base64.b64encode(content.encode()).decode(),
    }

    async with session.put(url, headers=headers, json=data) as response:
        if response.status in (200, 201):
            logging.info(f"在仓库 {repo_name} 中创建 README.md")
            return True
        else:
            error_response = await response.json()
            logging.info(
                f"在 {repo_name} 中创建 README.md 失败：{response.status}, {error_response}"
            )
            return False


async def update_readme(session, repo_name, content, branch):
    url = f"https://api.github.com/repos/{USERNAME}/{repo_name}/contents/README.md"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

    current_readme = await fetch_readme(session, repo_name, branch)
    sha = ""
    if current_readme:
        sha_url = url
        async with session.get(sha_url, headers=headers) as response:
            if response.status == 200:
                sha_info = await response.json()
                sha = sha_info["sha"]

    data = {
        "message": "更新 README.md 添加免责声明",
        "content": base64.b64encode(content.encode()).decode(),
        "sha": sha,
    }

    async with session.put(url, headers=headers, json=data) as response:
        if response.status in (200, 201):
            logging.info(f"在仓库 {repo_name} 中更新 README.md")
            return True
        else:
            error_response = await response.json()
            logging.info(
                f"在 {repo_name} 中更新 README.md 失败：{response.status}, {error_response}"
            )
            return False


async def process_repository(session, repo, to_modify, modified):
    repo_name = repo["name"]
    default_branch = repo["default_branch"]

    if repo.get("fork"):
        logging.info(f"仓库 {repo_name} 是一个 fork，跳过处理。")
        return  # 如果是fork，直接返回

    readme_content = await fetch_readme(session, repo_name, default_branch)
    new_content = ""

    if readme_content:
        logging.info(f"正在处理仓库: {repo_name}")
        new_content = re.sub(
            CAUTION_BLOCK_PATTERN, "", readme_content, flags=re.DOTALL
        ).strip()

    if (
        CAUTION_STATEMENT_CN not in new_content
        and CAUTION_STATEMENT_EN not in new_content
    ):
        new_content += CAUTION_STATEMENT_CN + CAUTION_STATEMENT_EN

    if readme_content is None:
        # 如果 README.md 不存在则创建
        new_content = CAUTION_STATEMENT_CN + CAUTION_STATEMENT_EN
        success = await create_readme(session, repo_name, new_content, default_branch)
        if success:
            modified.append(repo_name)
    elif new_content != readme_content:
        to_modify.append(repo_name)
        success = await update_readme(session, repo_name, new_content, default_branch)
        if success:
            modified.append(repo_name)
    else:
        logging.info(f"仓库 {repo_name} 不需要更改")

async def main():
    to_modify = []
    modified = []

    async with aiohttp.ClientSession() as session:
        repos = await fetch_repositories(session)
        tasks = [
            process_repository(session, repo, to_modify, modified) for repo in repos
        ]
        await asyncio.gather(*tasks)

        while len(to_modify) > 0 or len(modified) > 0:
            logging.info(f"待修改的仓库总数：{len(to_modify)}")
            logging.info(f"已修改的仓库总数：{len(modified)}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
