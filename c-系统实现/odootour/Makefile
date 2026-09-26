COMPOSE := docker compose
DB := tour20

-include .env
# 运行数据家目录（与 docker-compose.yml 的 ${ODOOTOUR_HOME} 保持一致）
ODOOTOUR_HOME ?= $(HOME)/odoo20tour
export

.PHONY: build up down ps logs init-db restart shell psql backup admin-hash sync dev-db dev-install dev-test dev-web

build:            ## 构建镜像（升级时先在 .env 换 ODOO_COMMIT）
	$(COMPOSE) build odoo

up:               ## 启动全栈
	$(COMPOSE) up -d

down:             ## 停止全栈
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f odoo

init-db:          ## 初始化空库 tour20（不含 demo；只跑一次）
	$(COMPOSE) run --rm odoo python3 /usr/lib/odoo/odoo-server/odoo-bin \
		-c /etc/odoo/odoo.conf \
		--db_host=db --db_user=odoo --db_password=$(POSTGRES_PASSWORD) \
		-d $(DB) --without-demo=True -i base --stop-after-init

restart:
	$(COMPOSE) restart odoo

shell:            ## odoo 容器内 bash
	$(COMPOSE) exec odoo bash

psql:             ## 连 tour20 库
	$(COMPOSE) exec db psql -U odoo -d $(DB)

backup:           ## pg_dump + filestore 存档到 $(ODOOTOUR_HOME)/backup
	@mkdir -p $(ODOOTOUR_HOME)/backup
	docker exec odootour-db pg_dump -U odoo $(DB) | gzip > $(ODOOTOUR_HOME)/backup/$(DB)-$(shell date +%Y%m%d-%H%M%S).sql.gz
	sudo tar czf $(ODOOTOUR_HOME)/backup/filestore-$(shell date +%Y%m%d-%H%M%S).tgz -C $(ODOOTOUR_HOME)/pg/odoo filestore

admin-hash:       ## 用 .env 的 ADMIN_PASSWD 生成 pbkdf2 哈希（手工替换 config/odoo.conf 的 admin_passwd）
	$(COMPOSE) exec odoo python3 -c "from passlib.context import CryptContext; import os; \
	print(CryptContext(schemes=['pbkdf2_sha512']).hash(os.environ['ADMIN_PASSWD']))"

# ---- V20 ta_* 开发工作流（影子库 tour20_dev 先行，验收后才装正式库 tour20）----
DEV_DB := tour20_dev
ODOO := python3 /usr/lib/odoo/odoo-server/odoo-bin
DBARGS := -c /etc/odoo/odoo.conf --db_host=db --db_user=odoo --db_password=$(POSTGRES_PASSWORD)
MODE ?= -i

sync:             ## modules/ → $(ODOOTOUR_HOME)/cust_addons（容器 /mnt/extra-addons）
	sudo rsync -a --delete --chown=100:102 modules/ $(ODOOTOUR_HOME)/cust_addons/

dev-db:           ## 初始化影子库 tour20_dev（不含 demo；重复执行会报已存在，属正常）
	$(COMPOSE) run --rm odoo $(ODOO) $(DBARGS) -d $(DEV_DB) --without-demo=True -i base --stop-after-init

dev-install:      ## 影子库装/升模块：make dev-install MODS=ta_base[,…] [MODE=-u]
	$(COMPOSE) run --rm odoo $(ODOO) $(DBARGS) -d $(DEV_DB) $(MODE) $(MODS) --stop-after-init --log-level=warn

dev-test:         ## 影子库跑测试：make dev-test MODS=ta_route（随 -u 触发模块 tests）
	$(COMPOSE) run --rm odoo $(ODOO) $(DBARGS) -d $(DEV_DB) -u $(MODS) --test-enable --stop-after-init --log-level=test

dev-web:          ## 影子库网页预览：http://127.0.0.1:8077（Ctrl+C 停止）
	$(COMPOSE) run --rm -p 127.0.0.1:8077:8069 odoo $(ODOO) $(DBARGS) -d $(DEV_DB) \
		--db-filter='^$(DEV_DB)$$' --http-port=8069
