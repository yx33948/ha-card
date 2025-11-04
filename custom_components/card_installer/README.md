# 🎴 卡片一键安装器 - Home Assistant 集成

一个Home Assistant自定义集成，可以从Git仓库（Gitee/GitHub）一键安装Lovelace卡片到您的Home Assistant实例。

## 📋 功能特性

- ✅ 从Gitee或GitHub仓库下载卡片文件
- ✅ 自动复制到Home Assistant的`www/community`目录
- ✅ 自动添加到Lovelace资源库
- ✅ 支持自动更新功能
- ✅ 提供服务接口，可通过自动化控制
- ✅ 支持从配置界面进行设置

## 🚀 安装方法

### 方式一：通过HACS安装（推荐）

1. 确保已安装[HACS](https://hacs.xyz/)
2. 在HACS中搜索"卡片一键安装器"或"Card Installer"
3. 点击安装
4. 重启Home Assistant

### 方式二：手动安装

1. 将`card_installer`文件夹复制到您的Home Assistant配置目录下的`custom_components`文件夹
   ```
   config/
   └── custom_components/
       └── card_installer/
           ├── __init__.py
           ├── manifest.json
           ├── config_flow.py
           ├── card_manager.py
           ├── const.py
           └── services.yaml
   ```

2. 重启Home Assistant
3. 进入 **配置** > **设备与服务** > **添加集成**
4. 搜索"卡片一键安装器"并添加

## ⚙️ 配置说明

### 初始配置

在添加集成时，需要配置以下选项：

- **仓库URL** (必需): Gitee或GitHub仓库地址
  - 示例: `https://gitee.com/username/repo` 或 `https://github.com/username/repo`
  
- **分支** (可选): 仓库分支，默认为`master`
  
- **自动更新** (可选): 是否启用自动更新，默认为`true`
  
- **更新间隔** (可选): 自动更新的间隔时间（秒），最小值为300秒（5分钟），默认3600秒（1小时）

### 仓库要求

您的Git仓库应该包含`.js`格式的卡片文件，例如：
```
your-repo/
├── button-card.js
├── mushroom-card.js
├── mini-graph-card.js
└── ...
```

## 🎮 使用方法

### 通过UI安装

1. 添加集成后，系统会自动从配置的仓库下载并安装所有卡片
2. 安装完成后，**重启Home Assistant**以使卡片生效
3. 在Lovelace编辑器中，您就可以使用这些卡片了

### 通过服务调用

集成提供了三个服务：

#### 1. `card_installer.install_cards`
安装所有卡片
```yaml
service: card_installer.install_cards
```

#### 2. `card_installer.update_cards`
更新已安装的卡片
```yaml
service: card_installer.update_cards
```

#### 3. `card_installer.remove_card`
移除指定的卡片
```yaml
service: card_installer.remove_card
data:
  filename: button-card.js
  # 或
  url: /local/community/button-card.js
```

### 自动化示例

```yaml
automation:
  - alias: "更新卡片"
    trigger:
      - platform: time
        at: "02:00:00"
    action:
      - service: card_installer.update_cards
```

## 📁 文件结构

安装后，卡片文件会存放在：
```
config/
├── www/
│   └── community/
│       ├── button-card.js
│       ├── mushroom-card.js
│       └── ...
└── .storage/
    └── lovelace_resources  # 资源配置文件
```

## ⚠️ 注意事项

1. **必须重启Home Assistant**: 安装或更新卡片后，需要重启Home Assistant才能使用新卡片
2. **仓库访问**: 确保您的Home Assistant可以访问配置的Git仓库（需要网络连接）
3. **文件格式**: 只支持`.js`格式的卡片文件
4. **自动更新**: 如果启用了自动更新，系统会定期检查并更新卡片文件

## 🔧 故障排查

### 卡片安装失败
- 检查仓库URL是否正确
- 确认仓库是公开的或Home Assistant有访问权限
- 查看日志文件获取详细错误信息

### 卡片无法使用
- 确认已重启Home Assistant
- 检查卡片文件是否正确下载到`www/community`目录
- 在Lovelace资源管理页面检查资源是否已添加

### 更新不工作
- 检查自动更新是否已启用
- 确认更新间隔设置合理
- 查看日志确认是否有错误

## 📞 支持

- 问题反馈: [GitHub Issues](https://github.com/your-repo/card-installer/issues)
- 文档: [完整文档](https://github.com/your-repo/card-installer)

## 📝 更新日志

### v1.0.0
- 初始版本
- 支持从Gitee/GitHub下载卡片
- 支持自动更新
- 提供服务接口

---

**提示**: 安装完成后记得重启Home Assistant！

