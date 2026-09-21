.PHONY: deps-check up down restart logs shell odoo-shell db-backup db-restore install uninstall

up:
	docker compose up -d
	@echo ""
	@echo "=== TMS Platform 启动中 ==="
	@echo "访问: https://tms.solepro.cloud （数据库管理端点已对公网关闭，见 config/ODOO_PIN.md 与 A0 报告）"
	@echo "master 口令：见 .env 的 ADMIN_PASSWD（哈希在 config/odoo.conf）"
	@echo "依赖与镜像 pin：make deps-check"
	@echo ""

down:
	docker compose down

restart:
	docker compose restart odoo

logs:
	docker compose logs -f --tail=100

# 运行期第三方依赖自检（缺 pandas 会让整个 registry 载入失败 → 全站 500）
deps-check:
	@docker exec tms-odoo python3 -c "import pandas, numpy, qifparse; print('deps ok', pandas.__version__, numpy.__version__)" \
	  || echo "FAIL: 依赖缺失，请 docker compose build odoo 后 up -d（不要 docker exec pip install）"

odoo-logs:
	docker exec tms-odoo tail -f /var/lib/odoo/odoo-server.log

shell:
	docker exec -it tms-odoo bash

odoo-shell:
	docker exec -it tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf

db-shell:
	docker exec -it tms-db psql -U odoo

# Install custom module
install:
	docker exec tms-odoo odoo -d tms -i tour_product --stop-after-init --config /etc/odoo/odoo.conf

# Update custom module
update:
	docker exec tms-odoo odoo -d tms -u tour_product --stop-after-init --config /etc/odoo/odoo.conf

# Restart odoo to reload code (dev mode)
reload:
	docker compose restart odoo

# Backup database
db-backup:
	@mkdir -p ./data/backups
	docker exec tms-db pg_dump -U odoo -Fc tms > ./data/backups/tms_$$(date +%Y%m%d_%H%M%S).dump
	@echo "备份完成: ./data/backups/"

# Cleanup (remove all data)
clean:
	docker compose down -v
	sudo rm -rf ./data/postgres ./data/odoo ./data/redis

# Show status
status:
	@docker compose ps
	@echo ""
	@docker exec tms-odoo cat /var/lib/odoo/odoo-server.log 2>/dev/null | tail -5 || true
