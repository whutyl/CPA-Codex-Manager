#!/usr/bin/env python3
"""
test_single_registration.py - 单账号注册测试脚本
用法:
    python test_single_registration.py \\
        --email-service freemail \\
        --freemail-api-key YOUR_KEY \\
        --freemail-url https://your.freemail.server/api \\
        --proxy http://YOUR_PROXY:PORT \\
        --cpa-url https://YOUR_CPA/api \\
        --cpa-token YOUR_CPA_TOKEN

环境变量也可替代命令行参数:
    export FREEMAIL_API_KEY=...
    export FREEMAIL_URL=...
    export CPA_API_URL=...
    export CPA_API_TOKEN=...
    export REGISTRATION_PROXY=http://...
"""

import os
import sys
import json
import argparse
import time
import logging
from pathlib import Path

# ── 参数解析 ────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="CPA 单账号注册测试")
parser.add_argument("--email-service", default=os.getenv("EMAIL_SERVICE", "freemail"),
                    choices=["freemail", "tempmail", "cloudmail"],
                    help="邮箱服务类型")
parser.add_argument("--freemail-api-key", default=os.getenv("FREEMAIL_API_KEY", ""),
                    help="Freemail API Key")
parser.add_argument("--freemail-url", default=os.getenv("FREEMAIL_URL", ""),
                    help="Freemail API URL")
parser.add_argument("--tempmail-api-key", default=os.getenv("TEMPMAIL_API_KEY", ""),
                    help="TempMail API Key")
parser.add_argument("--cloudmail-api-key", default=os.getenv("CLOUDMAIL_API_KEY", ""),
                    help="CloudMail API Key")
parser.add_argument("--cloudmail-url", default=os.getenv("CLOUDMAIL_URL", ""),
                    help="CloudMail API URL")
parser.add_argument("--proxy", default=os.getenv("REGISTRATION_PROXY", ""),
                    help="注册用代理 URL (http://host:port)")
parser.add_argument("--cpa-url", default=os.getenv("CPA_API_URL", ""),
                    help="CPA API URL")
parser.add_argument("--cpa-token", default=os.getenv("CPA_API_TOKEN", ""),
                    help="CPA API Token")
parser.add_argument("--browser-mode", default="protocol",
                    choices=["protocol", "headed"],
                    help="浏览器模式")
parser.add_argument("--max-retries", type=int, default=1,
                    help="最大重试次数")
args = parser.parse_args()

# ── 环境检查 ────────────────────────────────────────────────────────────────

REQUIRED = [
    ("邮箱服务 API Key", bool(getattr(args, f"{args.email_service.replace('-','_')}_api_key"))),
    ("代理", bool(args.proxy)),
    ("CPA URL", bool(args.cpa_url)),
    ("CPA Token", bool(args.cpa_token)),
]

print("=" * 60)
print("CPA-Codex-Manager 单账号注册测试")
print("=" * 60)
print(f"邮箱服务: {args.email_service}")
print(f"代理:     {args.proxy or '(未配置，使用直连)'}")
print(f"CPA URL:  {args.cpa_url or '(未配置，不上传CPA)'}")
print()

missing = [(name, ok) for name, ok in REQUIRED if not ok]
if missing:
    print("❌ 缺少必要配置:")
    for name, _ in missing:
        print(f"   - {name}")
    print()
    print("使用 --help 查看完整参数")
    sys.exit(1)

# ── 项目路径设置 ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# 设置必要环境变量（让项目代码能读到）
os.environ.setdefault("APP_DATA_DIR", str(PROJECT_ROOT / "data"))
os.environ.setdefault("APP_LOGS_DIR", str(PROJECT_ROOT / "logs"))
os.environ.setdefault("EMAIL_SERVICE", args.email_service)

# CPA 配置（让 cpa_upload 能工作）
if args.cpa_url:
    os.environ["CPA_API_URL"] = args.cpa_url
if args.cpa_token:
    os.environ["CPA_API_TOKEN"] = args.cpa_token

for d in ["data", "logs"]:
    (PROJECT_ROOT / d).mkdir(exist_ok=True)

# ── 日志配置 ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "logs" / "test_registration.log")
    ]
)
logger = logging.getLogger(__name__)

# ── 数据库初始化 ────────────────────────────────────────────────────────────

from src.database.init_db import initialize_database
initialize_database()
logger.info("数据库初始化完成")

# ── 准备邮箱服务 ────────────────────────────────────────────────────────────

def build_email_service(service_type: str, api_key: str, url: str = ""):
    from src.services import EmailServiceFactory, EmailServiceType

    if service_type == "freemail":
        if not url:
            logger.error("Freemail 需要 --freemail-url 参数")
            sys.exit(1)
        from src.services.freemail import FreemailService
        return FreemailService(api_key=api_key, base_url=url)

    elif service_type == "tempmail":
        from src.services.tempmail import TempMailService
        return TempMailService(api_key=api_key)

    elif service_type == "cloudmail":
        if not url:
            logger.error("CloudMail 需要 --cloudmail-url 参数")
            sys.exit(1)
        from src.services.cloud_mail import CloudMailService
        return CloudMailService(api_key=api_key, base_url=url)

    raise ValueError(f"不支持的邮箱服务: {service_type}")

email_svc = build_email_service(
    args.email_service,
    api_key=getattr(args, f"{args.email_service.replace('-','_')}_api_key"),
    url=getattr(args, f"{args.email_service.replace('-','_')}_url", "")
)

# ── 注册引擎 ────────────────────────────────────────────────────────────────

from src.core.register_v2 import RegistrationEngineV2
from src.core.registration_result import RegistrationResult

print()
print("=" * 60)
print("开始注册测试")
print("=" * 60)

engine = RegistrationEngineV2(
    email_service=email_svc,
    email_info=None,          # 由 email_service 内部创建
    proxy_url=args.proxy or None,
    max_retries=args.max_retries,
    browser_mode=args.browser_mode,
)

# 实时日志回调
def log_callback(msg: str):
    print(f"  [注册] {msg}")

# ── 执行注册 ────────────────────────────────────────────────────────────────

start = time.time()
result = engine.run(log_callback=log_callback)
elapsed = time.time() - start

print()
print("=" * 60)
print("注册结果")
print("=" * 60)
print(f"成功:     {result.success}")
print(f"邮箱:     {result.email}")
print(f"密码:     {result.password}")
print(f"账号 ID:  {result.account_id}")
print(f"错误:     {result.error_message or '无'}")
print(f"耗时:     {elapsed:.1f}s")
print("=" * 60)

if result.success and args.cpa_url and args.cpa_token:
    print()
    print("正在验证 CPA Token 有效性...")
    from src.core.upload.cpa_upload import verify_access_token_with_cpa
    verified, msg = verify_access_token_with_cpa(
        access_token=result.access_token,
        account_email=result.email,
    )
    print(f"CPA 验证: {'✅' if verified else '❌'} {msg}")

    if verified:
        print()
        print("尝试上传到 CPA...")
        from src.core.upload.cpa_upload import upload_to_cpa
        from src.database.session import get_db
        from src.database import crud
        from src.database.models import Account

        token_data = {
            "type": "codex",
            "email": result.email,
            "expired": "",
            "id_token": result.id_token or "",
            "account_id": result.account_id or "",
            "access_token": result.access_token,
            "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "refresh_token": result.refresh_token or "",
        }
        ok, msg2 = upload_to_cpa(token_data)
        print(f"CPA 上传: {'✅' if ok else '❌'} {msg2}")

        if ok:
            # 保存到数据库
            try:
                with get_db() as db:
                    account = crud.create_account(
                        db,
                        email=result.email,
                        password=result.password,
                        email_service=args.email_service,
                        account_id=result.account_id,
                        access_token=result.access_token,
                        refresh_token=result.refresh_token,
                        id_token=result.id_token,
                        extra_data=result.metadata,
                        source="test_registration",
                    )
                    account.cpa_uploaded = True
                    db.commit()
                    print(f"✅ 账号已入库，DB ID: {account.id}")
            except Exception as e:
                logger.error(f"数据库保存失败: {e}")

print()
if result.success:
    print("🎉 注册成功!")
else:
    print("❌ 注册失败，详情见上方日志")
    sys.exit(1)
