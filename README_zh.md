# 史密斯热水器 (A.O. Smith / AI-LiNK) - Home Assistant 集成

[English](README.md) | 中文

通过 AI-LiNK / Al-Link 云 API 将 A.O. Smith 电热水器接入 Home Assistant。

## 功能

- **热水器实体** - 开关机、温度控制（35-75°C）、运行模式（ECO/标准/增容）
- **开关** - 电源、预热、即热模式、杀菌、增容
- **传感器** - 当前水温、目标温度、加热状态、工作模式、故障代码等
- **预约加热（CircleTimer）** - 6 个时间段（每段 4 小时），配有圆形时钟选择卡片

## 安装

### HACS（推荐）

1. 打开 Home Assistant 中的 HACS
2. 进入 **集成** > **自定义仓库**（右上角三个点）
3. 添加仓库地址 `https://github.com/lolRustyNail/smith-ha`，类别选择 **Integration**
4. 搜索并安装 **Smith Water Heater**
5. 重启 Home Assistant

### 手动安装

1. 将 `custom_components/smith_water_heater/` 文件夹复制到 HA 的 `config/custom_components/` 目录下
2. 重启 Home Assistant

## 配置

### 手机号登录（推荐）

1. 进入 **设置** > **设备与服务** > **添加集成**
2. 搜索 **Smith Water Heater**
3. 选择 **手机号登录**
4. 输入注册 AI-LiNK 应用的手机号码
5. 如果需要完成安全验证，在浏览器中打开提示的链接，完成拼图验证
6. 输入手机收到的 6 位短信验证码
7. 完成！集成将自动获取所有会话信息

### 备选：手动粘贴会话 JSON

如果手机号登录不可用，仍然可以手动粘贴会话数据：

1. 使用 [mitmproxy](https://mitmproxy.org/) 抓取 API 流量（见下方说明）
2. 在集成设置中选择 **粘贴会话 JSON**
3. 粘贴包含 `auth_token`、`user_id`、`family_id`、`family_uk` 的 JSON

<details>
<summary>如何通过 mitmproxy 抓取会话数据</summary>

1. 在电脑上安装 mitmproxy
2. 在 MUMU 模拟器中配置代理指向 mitmproxy
3. 在模拟器中安装 mitmproxy 的 CA 证书
4. 打开 AI-LiNK 应用并登录
5. 抓取 `getHomepageV2` 请求头，找到 `Authorization: Bearer <token>` 字段
6. 提取以下会话信息：
   - `auth_token` - JWT Bearer 令牌
   - `user_id` - 用户 ID
   - `family_id` - 家庭 ID
   - `family_uk` - 家庭唯一标识

会话 JSON 格式示例：
```json
{
  "auth_token": "eyJhbGciOi...",
  "user_id": "12345678",
  "family_id": "87654321",
  "family_uk": "abcdef12"
}
```

</details>

## 预约加热圆形卡片

项目包含一个自定义的圆形时钟预约加热选择卡片。

### 安装卡片

将 `www/smith-water-heater/circle-timer-card.js` 复制到 HA 的 `config/www/smith-water-heater/` 目录下。

在 Lovelace 资源中添加：

```yaml
url: /local/smith-water-heater/circle-timer-card.js
type: module
```

### 使用卡片

在仪表盘中添加：

```yaml
type: custom:circle-timer-card
entity: select.你的预约加热实体ID
name: 预约加热
```

卡片特性：
- 圆形时钟分为 6 段：0-4点、4-8点、8-12点、12-16点、16-20点、20-24点
- 点击时间段切换选中/取消
- 支持全选和清除全部
- 绿色主题，选中的时间段高亮显示

> **注意**：由于热水器 API 不返回当前预约状态，卡片在刷新后会重置为全未选中。实际的预约设置以热水器为准。

## 支持的设备

- A.O. Smith 电热水器（productType: 17, deviceType: EWH-HGAWi）
- 其他 AI-LiNK 兼容设备可能可用，但未经测试

## 技术说明

- 云轮询间隔默认 60 秒
- 令牌自动刷新（主动检查 + 被动捕获响应头）
- 使用乐观更新模式，操作后立即反馈到界面
- 反重放签名：MD5 排序参数 + 防篡改头部

## 常见问题

**Q: 添加集成时提示 "cannot_connect"**
A: 检查网络是否能访问 `ailink-api.hotwater.com.cn`，确认 auth_token 未过期。

**Q: 温度设置后 HA 显示没变**
A: 这是正常的，使用了乐观更新模式，实际值会在下次轮询（约60秒）后同步。

**Q: 预约加热实体状态显示 unknown**
A: 这是已知限制，热水器 API 不返回 CircleTimer 的当前值。请使用圆形卡片来设置预约。

## 许可证

[MIT License](LICENSE)
