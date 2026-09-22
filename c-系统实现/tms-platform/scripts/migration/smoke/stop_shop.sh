#!/bin/bash
# 停 28169 冒烟服务。必须放在**文件**里跑：命令行内联 `pkill -f b1shop1` 会匹配到
# 执行它的 shell 自身，把自己的会话一起杀掉（实测 exit 143）。
pkill -f "odoo-bin -c odoo.conf -d b1shop1" && echo stopped || echo "no process"
