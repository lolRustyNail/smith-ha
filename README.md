# Smith Water Heater (A.O. Smith / AI-LiNK)

English | [中文](README_zh.md)

Home Assistant integration for A.O. Smith electric water heaters controlled via the AI-LiNK / Al-Link app (China).

## Features

- **Water Heater Entity** - Power on/off, temperature control (35-75°C), operation modes (ECO/Standard/Performance)
- **Switches** - Power, Preheat, Instant Heating, Disinfection, Increase Capacity
- **Sensors** - Current temperature, target temperature, heat status, work mode, error code, and more
- **Scheduled Heating (CircleTimer)** - 6 time slots (4 hours each) with a custom circular Lovelace card

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant
2. Go to **Integrations** > **Custom repositories** (three-dot menu)
3. Add `https://github.com/lolRustyNail/smith-ha` with category **Integration**
4. Install **Smith Water Heater**
5. Restart Home Assistant

### Manual

1. Copy `custom_components/smith_water_heater/` to your HA `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### Phone Login (Recommended)

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for **Smith Water Heater**
3. Select **手机号登录** (Phone Login)
4. Enter your phone number registered with the AI-LiNK app
5. If CAPTCHA verification is required, open the displayed URL in your browser and complete the puzzle
6. Enter the 6-digit SMS verification code received on your phone
7. Done! The integration will automatically obtain all session data

### Legacy: Manual Session Data

If phone login doesn't work, you can still paste session JSON manually:

1. Capture API traffic using [mitmproxy](https://mitmproxy.org/) (see below)
2. Select **粘贴会话 JSON** (Paste Session JSON) in the integration setup
3. Paste the JSON containing: `auth_token`, `user_id`, `family_id`, `family_uk`

<details>
<summary>How to capture session data via mitmproxy</summary>

1. Install mitmproxy on your PC
2. Set up a MUMU/Android emulator with the proxy
3. Install the mitmproxy CA certificate in the emulator
4. Open the AI-LiNK app and log in
5. Capture the `getHomepageV2` request headers - look for `Authorization: Bearer <token>`
6. Extract the session JSON with these fields:
   - `auth_token` - JWT Bearer token
   - `user_id` - Your user ID
   - `family_id` - Your family/home ID
   - `family_uk` - Your family unique key

</details>

## CircleTimer Lovelace Card

A custom circular schedule picker card is included. Add it to your dashboard:

```yaml
type: custom:circle-timer-card
entity: select.your_schedule_entity
name: 预约加热
```

Copy `www/smith-water-heater/circle-timer-card.js` to your HA `config/www/smith-water-heater/` directory, then add to your Lovelace resources:

```yaml
url: /local/smith-water-heater/circle-timer-card.js
type: module
```

## Supported Devices

- A.O. Smith electric water heaters (productType: 17, deviceType: EWH-HGAWi)
- Other AI-LiNK compatible devices may work but are untested

## Notes

- Cloud polling interval defaults to 60 seconds
- Token refresh is handled automatically (proactive + reactive)
- The CircleTimer state cannot be read from the API, so the card maintains local state
