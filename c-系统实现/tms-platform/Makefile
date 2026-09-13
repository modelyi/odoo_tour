.PHONY: up down restart logs shell odoo-shell db-backup db-restore install uninstall

up:
	docker compose up -d
	@echo ""
	@echo "=== TMS Platform 启动中 ==="
	@echo "访问: http://tms.solepro.cloud"
	@echo "首次访问需在数据库管理器中创建数据库"
	@echo "Master Password: tms_admin_2026"
	@echo ""

down:
	docker compose down

restart:
	docker compose restart odoo

logs:
	docker compose logs -f --tail=100

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
