#!/bin/bash

echo "=== 导游门户功能测试脚本 ==="
echo ""

# 测试 1: 检查模块是否安装
echo "1. 检查模块安装状态..."
docker exec tms-db psql -U odoo -d tms -t -c "SELECT name, state FROM ir_module_module WHERE name='tour_guide_portal';" | grep -q "installed"
if [ $? -eq 0 ]; then
    echo "   ✓ 模块已安装"
else
    echo "   ✗ 模块未安装"
    exit 1
fi

# 测试 2: 检查路由是否可访问
echo ""
echo "2. 测试门户路由..."
ROUTES=(
    "/my/guide"
    "/my/guide/dispatches"
    "/my/guide/commissions"
    "/my/guide/loans"
    "/my/guide/expenses"
)

for route in "${ROUTES[@]}"; do
    status=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Odoo-Database: tms" "http://localhost:8070${route}")
    if [ "$status" == "302" ] || [ "$status" == "200" ]; then
        echo "   ✓ ${route} (HTTP ${status})"
    else
        echo "   ✗ ${route} (HTTP ${status})"
    fi
done

# 测试 3: 检查数据库表
echo ""
echo "3. 检查数据表..."
TABLES=("tour_guide" "tour_commission" "tour_guide_loan" "hr_expense")
for table in "${TABLES[@]}"; do
    count=$(docker exec tms-db psql -U odoo -d tms -t -c "SELECT count(*) FROM ${table};" | xargs)
    echo "   ✓ ${table}: ${count} 条记录"
done

# 测试 4: 检查门户相关字段
echo ""
echo "4. 检查门户字段..."
docker exec tms-db psql -U odoo -d tms -c "\d tour_guide" | grep -q "portal_user_id"
if [ $? -eq 0 ]; then
    echo "   ✓ tour_guide.portal_user_id 字段存在"
else
    echo "   ✗ tour_guide.portal_user_id 字段不存在"
fi

docker exec tms-db psql -U odoo -d tms -c "\d tour_commission" | grep -q "access_url"
if [ $? -eq 0 ]; then
    echo "   ✓ tour_commission.access_url 字段存在"
else
    echo "   ✗ tour_commission.access_url 字段不存在"
fi

# 测试 5: 检查安全规则
echo ""
echo "5. 检查安全规则..."
rule_count=$(docker exec tms-db psql -U odoo -d tms -t -c "SELECT count(*) FROM ir_rule WHERE name LIKE '%portal%';" | xargs)
echo "   ✓ 找到 ${rule_count} 条门户相关规则"

# 测试 6: 检查视图
echo ""
echo "6. 检查视图..."
view_count=$(docker exec tms-db psql -U odoo -d tms -t -c "SELECT count(*) FROM ir_ui_view WHERE name LIKE '%portal%guide%';" | xargs)
echo "   ✓ 找到 ${view_count} 个门户视图"

echo ""
echo "=== 测试完成 ==="
echo ""
echo "下一步："
echo "1. 登录 Odoo 后台: http://localhost:8070/web/login"
echo "2. 进入导游档案，选择一个有 partner_id 的导游"
echo "3. 点击'发送门户邀请'按钮"
echo "4. 使用门户用户登录测试: http://localhost:8070/my/guide"
