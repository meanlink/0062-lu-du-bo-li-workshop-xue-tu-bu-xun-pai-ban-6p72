# 炉读 · 玻璃工坊学徒补训排班

河湾玻璃工坊有 4 位导师和 12 名轮训学徒。导师原先用表格记三项课堂评分，再在群里安排辅导。轮训资格、旧观察与余席分散存放，容易把新观察漏掉、安排错方向或超售席位。本工具把课堂观察接到导师辅导排班，下游为教务和值班导师。

## 一天的工作顺序

1. 09:10 核对徐晨 A-04 与旁听学徒 A-11 的名册。
2. 10:05 拒绝把旁听记录 O-302 写入正式轮训。
3. 11:40 从周二轮训记录.csv 登记徐晨 O-301，评分 9、3、8。
4. 12:15 计算补训归因，检查交接记录方向和判别余量。
5. 13:00 尝试把徐晨排入工位辅导 C-16，方向不符时退回。
6. 13:25 复核员签核 C-14 的 14:00 交接辅导。
7. 13:40 如需退出轮训，先撤销席位；教务侧再次核对余量。
8. 15:10 导师临时停课时，复核员在辅导排班关闭班次：按原签核先后把学徒迁往同方向最近的后续余席，未迁成者保留原签核依据进入待补；后续班次撤席时先按原签核顺序补待补，再接新签核。

## 停课与待补口径

- 关闭班次在单事务内完成，行级锁串行化签核与停课，任何并发组合下席位占用都不超过容量。
- 迁移只选同方向、开始时间晚于停课班次且未关闭的余席班次，取时间最近者；其他班次已签人员不受影响。
- 迁席与补位记录始终沿用最早的原签核依据（原班次、原签核人、原签核时间），链式停课也不覆盖。
- 无后续余席的学徒进入 `coaching_makeup` 待补队列；同方向有待补者期间，新签核一律让位，撤席产生的余席自动按原签核顺序补位。
- 重复提交停课请求是幂等的：已关闭班次直接返回当前迁移与待补现状，不会重复迁席。
- 排班页面可查每位受影响学徒的去向（迁入班次）或待补状态，以及对应的原签核依据。

## 测试

```sh
# 需要一个可连接的 PostgreSQL；schema 自动以幂等迁移方式应用
DATABASE_URL=postgresql://app@127.0.0.1:17956/business_test python3 tests/test_closures.py
DATABASE_URL=postgresql://app@127.0.0.1:17956/business_test python3 tests/test_api.py
```

领域集成测试覆盖迁移顺序、待补依据、撤席补位、重复停课幂等、链式停课以及停课与签核并发的超售压测；API 测试覆盖鉴权、响应结构与端到端补位。

## 算法口径

等先验对角线性判别分析。以九条历史导师标注为参考，计算各类训练分数中心与三维度合并类内方差（下限 0.25）。距离是标准化平方偏差之和，最低者为推荐方向。第二低与最低距离之差为判别余量。缺观察、样本不足或余量小于 1 时不签核。使用最新日期及记录编号决定输入版本。

## 上手

```sh
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
docker compose down --remove-orphans
```

前端走本机 **18456**，API 走 **19456**，PostgreSQL 走 **17956**。本地开发可在安装 Python 3.11、PostgreSQL 和 Redis 后配置与 Compose 相同的环境变量，在 backend 运行 `uvicorn app:app --reload`，前端以 Nginx 同源代理启动。

| 角色 | 邮箱 | 业务权限 |
|---|---|---|
| 录入员 | operator@demo.local | 记录实际观察、计算补训归因 |
| 复核员 | reviewer@demo.local | 校验在训资格、签核、撤销班次或停课关闭班次 |
| 查阅员 | viewer@demo.local | 查名册、观察、归因、签排 |

三个演示账号默认密码均为 `Demo2026!`。使用本地合成样本，seed 只插入缺失的自然键。关闭 `SEED_DEMO` 可跳过自动 seed。使用自己的 `JWT_SECRET`、`POSTGRES_PASSWORD` 和 `DEMO_PASSWORD` 部署。

| 目录 | 技术与职责 |
|---|---|
| backend | Python 3.11 / FastAPI，使用 PostgreSQL 16；Worker 轮询持久化队列，Redis 为登录限流及健康检查提供支持 |
| frontend | Nginx、HTML、CSS、JavaScript ES modules，HTTP 同源代理 |
| docker-compose.yml | 5 服务及健康检查、独立卷；Redis 与 worker 无宿主端口 |

角色、作业状态在 `backend/core.py`、`frontend/base.js` 定义，在 `backend/core.py`（鉴权、队列）与 `backend/worker.py` 使用。领域阶段由数据库约束与业务服务维护，`frontend/view.js` 负责显示。接口输出为最新已提交状态。

演示按学员得分进行辅导安排，记录是课堂观察。历史锚点是合成数据；余量用于工作坊人工复核。

MIT License
