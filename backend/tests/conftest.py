import os

# 单元/接口测试不依赖 Postgres：测试内自建 sqlite 引擎，这里只让 app.database
# 的模块级全局 engine 能在未设 DATABASE_URL 的环境里成功创建（测试并不使用它）。
os.environ.setdefault("DATABASE_URL", "sqlite://")
