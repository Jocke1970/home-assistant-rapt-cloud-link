# RAPT Cloud Link for Home Assistant — BrewAssistant branch

![hacs_badge](https://img.shields.io/badge/HACS-Custom-blue.svg)

> [!IMPORTANT]
> This is the **BrewAssistant-adapted branch** of RAPT Cloud Link.
> It adds BrewAssistant metadata, BLE/control-device temperature handling and
> diagnostic sensors while retaining the original `rapt_cloud_link` integration
> domain. See [BREWASSISTANT_CHANGES.md](BREWASSISTANT_CHANGES.md) for the complete
> change history, current limitations and upstream synchronization checklist.
>
> Development branch: `ba/brewassistant-rapt-cloud-link`  
> Upstream: [`berra200/home-assistant-rapt-cloud-link`](https://github.com/berra200/home-assistant-rapt-cloud-link)  
> BrewAssistant beta.12 requires this fork's **operational profile runtime**, not the upstream-only `main` code.

This is a custom integration for Home Assistant that connects to [RAPT Cloud](https://app.rapt.io) and allows you to monitor and control your BrewZilla, RAPT Pill, or other RAPT-compatible brewing devices.

## Credits

RAPT Cloud Link was originally created by [berra200](https://github.com/berra200).
This fork retains the original project's MIT license and copyright notice.
The BrewAssistant-specific adaptations are maintained by
[Jocke1970](https://github.com/Jocke1970) and are documented in
[BREWASSISTANT_CHANGES.md](BREWASSISTANT_CHANGES.md).

## Features

- Cloud polling for real-time updates from your devices.
- Supports multiple device types including:
  - BrewZilla (temperature, heating, pump, etc.)
  - RAPT Pill (gravity, temperature, battery)
  - Bonded devices (RAPT Bluetooth Thermometer)
- Displays sensor values such as:
  - Temperature
  - Specific Gravity
  - Battery
  - Target Temperature
  - Heating State
  - Pump State
- Control entities:
  - Heating switch
  - Pump switch
  - Heating Utilization
  - Pump Utilization
  - Target Temperature
- BrewAssistant adaptation: an operational BrewZilla `Profile Active` binary sensor
  with a `ba_source` marker, session/current-step/next-step metadata, and
  `rapt_cloud_link.start_brewzilla_profile` / `end_brewzilla_profile` services.
  The binary sensor's actual entity ID can include the device name. Discover it
  by `ba_source: rapt_cloud_link_brewzilla_profile_runtime`; do not assume that
  every Home Assistant installation uses the same entity ID.

## Installation (via HACS) — BrewAssistant RCL prerelease

1. Back up your Home Assistant configuration and current RCL integration.
   Do not run this replacement during an active heating or pumping operation.
2. In HACS, identify the **existing** RAPT Cloud Link repository and which URL
   it uses. The upstream and this fork both use the domain `rapt_cloud_link`;
   do **not** install them as two independent integrations simultaneously.
3. Make sure HACS uses this fork's custom repository:
   `https://github.com/Jocke1970/home-assistant-rapt-cloud-link` (category: Integration).
   If HACS is currently tracking upstream, change/remove the old repository
   entry as appropriate **without deleting the existing HA integration entry
   or its credentials**. Back up first.
4. Enable prereleases if your HACS version requires it, and explicitly install
   tag `v0.5.0-beta.1` from this fork's published GitHub prerelease. Do not
   install the untagged `main`, `ba/...` or `release/...` development branch
   for a physical test.
5. Restart Home Assistant while the BrewZilla is inactive. Confirm the installed
   `custom_components/rapt_cloud_link/manifest.json` says `0.5.0-beta.1`.
6. In Developer Tools → States, locate the RCL `Profile Active` binary sensor
   (search for the `ba_source` marker). When a RAPT profile is **already active**,
   confirm `profile_contract_complete`, `profile_session_id`, `step_id`,
   `step_target_temperature`, and the actual entity ID. Confirm BrewAssistant
   recognizes RAPT before any supervised heating or pump command.
7. If anything is missing or reports `unknown`, do not bypass source-authority
   protections. Keep heat and pump disabled and collect diagnostics.

The prerelease supports observation and validation first. A successful HACS
installation, green CI or an accepted RCL cloud API request does **not** prove
that the hardware outputs are physically safe.

## Configuration

- You need an **API key** from RAPT Cloud (not just a password) to authenticate.
- The integration automatically discovers your devices linked to your account.

## Upcoming Features

- Additional device types and enhanced sensor/control options.
- Improved error handling and stability.

## Tips & Notes

- The integration polls your devices periodically to provide real-time updates.
- Make sure your API key has the correct permissions in RAPT Cloud.
- Feedback and contributions are welcome via GitHub issues and pull requests.

## License

[MIT](LICENSE)
