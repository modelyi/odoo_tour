COMPOSE := docker compose
DB := tour20

-include .env
# 运行数据家目录（与 docker-compose.yml 的 ${ODOOTOUR_HOME} 保持一致）
ODOOTOUR_HOME ?= $(HOME)/odootour
export

.PHONY: build up down ps logs init-db restart shell psql backup admin-hash

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
