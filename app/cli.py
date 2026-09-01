"""本地维护命令。敏感输入只通过交互式终端读取。"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.auth.service import auth_service
from app.db.engine import db_session, init_db


def _password_pair() -> str:
    password = getpass.getpass("管理员密码（至少 12 位）：")
    confirmation = getpass.getpass("再次输入密码：")
    if password != confirmation:
        raise ValueError("两次输入的密码不一致")
    return password


def create_admin(username: str) -> None:
    init_db()
    with db_session() as db:
        user = auth_service.create_admin(db, username, _password_pair())
    print(f"管理员 {user.username} 已创建。")


def reset_password(username: str) -> None:
    init_db()
    with db_session() as db:
        auth_service.reset_password(db, username, _password_pair())
    print(f"管理员 {username.strip().lower()} 的密码已重置，旧会话已失效。")


def knowledge_rebuild(confirm_dimension_change: bool) -> None:
    if not confirm_dimension_change:
        raise ValueError("此维护操作必须显式提供 --confirm-dimension-change")
    print("维护入口已确认。请先备份 Milvus 数据，再从应用的知识库页面执行受控重建。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shopify AI Assistant 本地管理工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-admin", help="交互创建本地管理员")
    create.add_argument("--username", required=True)

    reset = subparsers.add_parser("reset-password", help="交互重置管理员密码")
    reset.add_argument("--username", required=True)

    rebuild = subparsers.add_parser("knowledge-rebuild", help="确认向量维度变更维护")
    rebuild.add_argument("--confirm-dimension-change", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "create-admin":
            create_admin(args.username)
        elif args.command == "reset-password":
            reset_password(args.username)
        elif args.command == "knowledge-rebuild":
            knowledge_rebuild(args.confirm_dimension_change)
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
