# 卡片一键安装器

从Git仓库一键安装Home Assistant Lovelace卡片。

## 使用方法

1. 在Git仓库（Gitee或GitHub）中放置您的卡片文件（.js格式）
2. 添加此集成，输入仓库URL
3. 系统会自动下载并安装所有卡片
4. 重启Home Assistant后即可使用

## 支持的服务

- `install_cards`: 安装所有卡片
- `update_cards`: 更新已安装的卡片
- `remove_card`: 移除指定卡片

