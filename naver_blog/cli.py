"""CLI entry point for naver-blog-publisher."""

import asyncio
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import click

from naver_blog.session import DEFAULT_SESSION_PATH

SESSION_PATH_HELP = "Session file path."


def get_session_path(ctx_param: str | None) -> str:
    return ctx_param or os.environ.get("NAVER_SESSION_PATH", DEFAULT_SESSION_PATH)


def _get_api(session_path: str):
    from naver_blog.api import NaverBlogApi
    blog_id = os.environ.get("NAVER_BLOG_ID")
    api = NaverBlogApi.from_session_file(session_path, blog_id)
    if not api.blog_id:
        api.init_blog()
    return api


@click.group()
@click.version_option(package_name="naver-blog-publisher")
def cli():
    """네이버 블로그 자동 발행 도구."""


@cli.command()
@click.option("--manual", is_flag=True, help="수동 로그인 (브라우저에서 직접 로그인).")
@click.option("--username", envvar="NAVER_USERNAME", help="Naver ID.")
@click.option("--password", envvar="NAVER_PASSWORD", help="Naver password.")
@click.option("--session-path", default=None, help=SESSION_PATH_HELP)
def login(manual, username, password, session_path):
    """네이버 로그인 후 세션 저장."""
    from naver_blog.auth import login as do_login
    sp = get_session_path(session_path)
    asyncio.run(do_login(username=username, password=password, manual=manual, session_path=sp))


@cli.command("auth-status")
@click.option("--session-path", default=None, help=SESSION_PATH_HELP)
def auth_status(session_path):
    """저장된 세션의 유효성 확인."""
    from naver_blog.session import validate_session
    sp = get_session_path(session_path)
    if validate_session(sp):
        click.echo("✅ 세션이 유효합니다.")
    else:
        click.echo("❌ 세션이 유효하지 않습니다. 'naver-blog login'으로 다시 로그인하세요.")
        sys.exit(1)


@cli.command()
@click.option("--session-path", default=None, help=SESSION_PATH_HELP)
def categories(session_path):
    """블로그 카테고리 목록 조회."""
    sp = get_session_path(session_path)
    api = _get_api(sp)
    cats = api.get_categories()
    for cat in cats:
        click.echo(f"  [{cat['id']}] {cat['name']}")


@cli.command()
@click.argument("markdown_file", type=click.Path(exists=True))
@click.option("--category", type=int, default=0, help="카테고리 번호.")
@click.option("--tags", default="", help="태그 (쉼표 구분).")
@click.option("--private", "is_private", is_flag=True, help="비공개 발행.")
@click.option("--session-path", default=None, help=SESSION_PATH_HELP)
def publish(markdown_file, category, tags, is_private, session_path):
    """마크다운 파일을 네이버 블로그에 발행."""
    from naver_blog.converter import md_to_html

    sp = get_session_path(session_path)
    api = _get_api(sp)
    click.echo(f"📝 블로그: {api.blog_id}")

    # Read and convert markdown
    md_path = Path(markdown_file)
    md_content = md_path.read_text(encoding="utf-8")
    title, html, images = md_to_html(md_content, base_dir=str(md_path.parent))

    if not title:
        click.echo("⚠️  제목을 찾을 수 없습니다. 첫 번째 # 헤딩을 사용하세요.")
        sys.exit(1)

    click.echo(f"📄 제목: {title}")
    click.echo(f"📝 HTML: {len(html)} chars, 이미지: {len(images)}개")

    # Upload images if any
    image_components = []
    if images:
        click.echo(f"🖼️  이미지 업로드 중...")
        info = api.get_editor_info(category)
        token = info["token"]
        for i, img_path in enumerate(images):
            if Path(img_path).exists():
                try:
                    img_data = api.upload_image(img_path, token)
                    comp = api.create_image_component(img_data, represent=(i == 0))
                    image_components.append(comp)
                    click.echo(f"   ✅ {Path(img_path).name} ({img_data['width']}x{img_data['height']})")
                except Exception as e:
                    click.echo(f"   ❌ {Path(img_path).name}: {e}")
            else:
                click.echo(f"   ⚠️  파일 없음: {img_path}")

    # HTML → SE components
    click.echo("🔄 SE 컴포넌트 변환...")
    components = api.html_to_components(html)
    click.echo(f"   {len(components)} 컴포넌트")

    # Prepend image components
    if image_components:
        components = image_components + components

    # Publish
    open_type = 0 if is_private else 2
    click.echo(f"🚀 발행 중... ({'비공개' if is_private else '공개'})")
    result = api.publish_post(
        title=title,
        components=components,
        category_no=category,
        tags=tags,
        open_type=open_type,
    )

    if result["success"]:
        click.echo(f"✅ 발행 성공! {result['url']}")
    else:
        click.echo(f"❌ 발행 실패: {result['raw']}")
        sys.exit(1)


@cli.command("list-posts")
@click.option("--limit", default=10, help="조회할 글 수.")
@click.option("--session-path", default=None, help=SESSION_PATH_HELP)
def list_posts(limit, session_path):
    """최근 블로그 글 목록 조회."""
    sp = get_session_path(session_path)
    api = _get_api(sp)
    posts = api.list_posts(limit)
    if not posts:
        click.echo("글이 없습니다.")
        return
    for post in posts:
        title = unquote(post.get("title", "").replace("+", " "))
        log_no = post.get("logNo", "")
        date = post.get("addDate", "")
        click.echo(f"  [{log_no}] {title}  ({date})")


def main():
    cli()


if __name__ == "__main__":
    main()
