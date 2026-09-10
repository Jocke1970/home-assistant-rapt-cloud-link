# BrewAssistant-specific changes

This document describes the custom changes carried by the
`ba/brewassistant-rapt-cloud-link` branch of
[`Jocke1970/home-assistant-rapt-cloud-link`](https://github.com/Jocke1970/home-assistant-rapt-cloud-link).

It exists so the BrewAssistant additions can be identified, tested and
reapplied when the fork is synchronized with upstream.

## Repository and branch model

- Fork: `Jocke1970/home-assistant-rapt-cloud-link`
- Upstream: `berra200/home-assistant-rapt-cloud-link`
- Upstream-tracking branch in the fork: `main`
- BrewAssistant branch: `ba/brewassistant-rapt-cloud-link`
- Home Assistant integration domain remains `rapt_cloud_link`

The BrewAssistant changes should stay isolated on the `ba/...` branch.
Upstream updates should first be brought into `main`, then merged or
rebased into the BrewAssistant branch and verified there.

## Current branch delta

As of 2026-09-10, the BrewAssistant branch carries the original five
BrewAssistant functional commits plus later maintenance and discovery work.
The BrewAssistant source changes remain concentrated in:

- `custom_components/rapt_cloud_link/sensor.py`

The original five BrewAssistant commits, oldest first, are:

1. [`25db2b0`](https://github.com/Jocke1970/home-assistant-rapt-cloud-link/commit/25db2b01b446b03f47c876a121cba5d11fd22f88)
   — Add BrewAssistant metadata for bonded BLE temperatures
2. [`cb766ff`](https://github.com/Jocke1970/home-assistant-rapt-cloud-link/commit/cb766ff8c53e4029da8aae57583a60fea904ca8f)
   — Add bonded devices debug sensor
3. [`b948c8d`](https://github.com/Jocke1970/home-assistant-rapt-cloud-link/commit/b948c8d3a1dee79af0c0e2917c1b04f1f29675b8)
   — Add BrewZilla payload debug sensor
4. [`a56fcb2`](https://github.com/Jocke1970/home-assistant-rapt-cloud-link/commit/a56fcb223d209922ab107b951635001ebaf44b33)
   — Add BrewZilla control device and BLE thermometer sensors
5. [`0906e2a`](https://github.com/Jocke1970/home-assistant-rapt-cloud-link/commit/0906e2a4ba167e29abed491a000a7dec8b677fd0)
   — Prefer valid BrewZilla telemetry control-device temperature

## Functional changes

### 1. BrewAssistant metadata on temperature sources

The existing BrewZilla internal-temperature sensor now exposes:

- `ba_source: rapt_cloud_link_brewzilla_internal`
- `ba_temperature_role: wort_or_kettle_temperature`
- `raw_device_id`

Bonded-device sensors expose common discovery metadata where available:

- `ba_source: rapt_cloud_link_bonded_device`
- `device_type`
- `raw_device_id`
- `parent_device_id`
- `updated_at`
- `payload_keys`
- `telemetry_keys`

Bonded temperature sensors additionally expose:

- `ba_temperature_role: candidate_mash_temperature`

Values can be read from either the root device payload or the first
telemetry-like object under `telemetry`, `telemetries`, `readings` or
`values`. Numeric bonded-device values are normalized and rounded to one
decimal place.

### 2. Bonded-device connection sensor

A `BondedDeviceConnectionStateSensor` is created for each supported bonded
device.

- unique suffix: `connection_state`
- possible values: `Connected`, `Disconnected`, `Unknown`
- includes the common BrewAssistant bonded-device metadata

### 3. Bonded-device discovery diagnostics

The integration always creates a diagnostic sensor named:

- `RAPT Cloud Link Bonded Devices Debug`
- unique ID: `rapt_cloud_link_bonded_devices_debug`

Its state is the number of bonded devices returned by the coordinator. Its
attributes summarize device IDs, names, types, temperature, battery,
connection state, parent relationship, timestamps and available payload
keys.

This sensor was added because the RAPT Cloud bonded-device endpoint returned
zero devices during the original BLE thermometer investigation. It is
diagnostic and is not itself a process-temperature source.

### 4. BrewZilla payload diagnostics

The integration always creates a diagnostic sensor named:

- `RAPT Cloud Link BrewZilla Debug`
- unique ID: `rapt_cloud_link_brewzilla_debug`

Its state is the number of BrewZilla devices returned by the coordinator.
Attributes expose the payload structure and useful values including:

- internal and control-device temperatures
- root and telemetry control-device temperature candidates
- selected temperature source and rejection reason
- control-device type and MAC address
- internal-sensor setting and sensor differential
- target temperature and connection state
- heating, pump and utilization values
- root and telemetry payload keys
- additional possible external-temperature fields
- bounded active-profile/session discovery metadata under `profile_runtime`

This sensor is intended for troubleshooting changes in the RAPT Cloud
payload without dumping the complete raw payload into Home Assistant state.

### 5. Dedicated BrewZilla control-device temperature sensor

A `BrewZillaControlDeviceTemperatureSensor` is added for each BrewZilla.

- name suffix: `Control Device Temperature`
- unique suffix: `control_device_temperature`
- `ba_temperature_role: candidate_mash_temperature`
- `ba_sensor_role: brewzilla_control_device_temperature`
- `ba_source: rapt_cloud_link_brewzilla_control_device`

It also exposes the RAPT control-device type, MAC address, internal-sensor
setting, sensor differential and temperature-selection diagnostics.

### 6. Logical RAPT BLE thermometer sensor

A `BrewZillaBleThermometerTemperatureSensor` is also added for each
BrewZilla. It is a logical Home Assistant sensor backed by the BrewZilla
`controlDeviceTemperature` payload; it is not populated from a separately
discovered bonded-device record.

- model: `RAPT BLE Thermometer`
- name suffix: `BLE Thermometer Temperature`
- unique suffix: `ble_thermometer_temperature`
- `ba_temperature_role: mash_temperature`
- `ba_sensor_role: ble_thermometer_temperature`
- `source_payload_key: controlDeviceTemperature`
- `linked_brewzilla_id`

The dedicated control-device sensor and logical BLE thermometer sensor
currently expose the same selected value but carry different semantic roles
for BrewAssistant.

### 7. Control-device temperature selection

RAPT Cloud may expose `controlDeviceTemperature` both at the BrewZilla
payload root and inside telemetry.

The branch applies this selection order:

1. use a valid telemetry value;
2. otherwise use a valid root value;
3. otherwise expose no temperature.

Telemetry is preferred because it is normally the fresher cloud
observation. Missing, non-numeric and `0.0` values are rejected; the
BrewZilla API can return `0.0` when no real cloud-side BLE temperature is
available.

Diagnostic attributes include:

- `root_control_device_temperature`
- `telemetry_control_device_temperature`
- `selected_control_device_temperature`
- `selected_control_device_temperature_source`
- `ba_value_rejected`
- `ba_reject_reason: control_device_temperature_zero_or_invalid`

### 8. Active BrewZilla profile/session discovery

A live BrewZilla test on 2026-09-10 established an important distinction:

- merely downloading a RAPT brewing profile to the BrewZilla did not add
  profile-related fields to the `GetBrewZillas` payload;
- once the profile was started on the BrewZilla, the root payload exposed
  `activeProfileId`, `activeProfileStepId` and `activeProfileSession`;
- active telemetry exposed `profileId` and `profileStepId`.

The BrewZilla debug sensor therefore includes a bounded `profile_runtime`
snapshot intended to discover the exact runtime contract without exposing
the complete raw profile/session object.

The snapshot includes, where available:

- root `active_profile_id` and `active_profile_step_id`;
- telemetry profile/session identifiers and progress candidates;
- `activeProfileSession` keys and selected timing fields;
- nested profile ID/name/keys when the session embeds a profile object;
- profile step count and the union of available step keys;
- a maximum 20-step preview containing only process-relevant fields such as
  target temperature, control/end/duration types, pump settings, heating
  utilisation, PID state and sensor differential.

This is discovery instrumentation only. It does not yet make a RAPT profile
the BrewAssistant process source and it does not change BrewZilla control.

## BrewAssistant usage intent

The added metadata distinguishes the two hot-side temperature roles:

- BrewZilla internal temperature: kettle/wort temperature and the permanent
  BrewZilla temperature source.
- RAPT BLE/control-device temperature: external process-temperature
  candidate, primarily used as the mash sensor when a valid value exists.

BrewAssistant owns/uses the external process sensor from Heat strike through
Mash, Mash out, Sparge and Pre-boil. It releases that sensor when Boil starts.
During Chill and Transfer the Cooling/CFC backend may use the same physical
BLE thermometer as the CFC wort-out temperature. BrewZilla's internal
temperature remains available throughout the brew day.

For active RAPT brewing profiles, the working architecture is that the
BrewZilla remains the local profile executor while BrewAssistant observes
and supervises the active profile/session through RAPT Cloud Link. The exact
runtime mapping will be implemented in BrewAssistant only after the live
payload contract has been verified.

That lifecycle is implemented in BrewAssistant. This fork only makes the
RAPT data and source metadata available to Home Assistant.

## Known limitations

- Availability depends on the fields returned by RAPT Cloud. The original
  bonded-device endpoint returned no BLE thermometer records.
- The logical BLE sensor can only show a value when BrewZilla's
  `controlDeviceTemperature` is present and valid.
- A zero value is intentionally treated as unavailable, not as a real
  process temperature.
- The two dedicated external-temperature sensors currently mirror the same
  selected payload value.
- Profile/session discovery currently relies on fields present in the
  `GetBrewZillas` response while a local BrewZilla profile is active.
- The `profile_runtime` step preview is capped at 20 steps and intentionally
  excludes unknown/raw nested content.
- The debug sensors can expose device identifiers, MAC addresses and payload
  structure in Home Assistant state attributes. Treat exported diagnostics
  accordingly.
- All custom code currently lives in `sensor.py`, so upstream edits to that
  file are the most likely source of merge conflicts.

## Upstream synchronization checklist

1. Fetch `berra200/home-assistant-rapt-cloud-link`.
2. Update the fork's `main` from upstream `main`.
3. Merge or rebase the updated `main` into
   `ba/brewassistant-rapt-cloud-link`.
4. Review every conflict in `custom_components/rapt_cloud_link/sensor.py`.
5. Compare `main...ba/brewassistant-rapt-cloud-link` and update this
   document if the branch delta changed.
6. Validate Python syntax and Home Assistant integration setup.
7. In Home Assistant, verify:
   - ordinary upstream BrewZilla/Pill entities still load;
   - both debug sensors load;
   - bonded connection entities load when bonded devices exist;
   - BrewZilla internal-temperature metadata is present;
   - control-device and logical BLE temperatures select telemetry first;
   - zero/invalid control-device values become unavailable and carry the
     rejection diagnostics;
   - `profile_runtime` stays structurally safe when no profile is active;
   - when a BrewZilla profile is active, the profile/session discovery fields
     reflect the root and telemetry payload.
8. Commit the synchronization and any documentation update to the
   BrewAssistant branch.

## Maintenance rule

Any future BrewAssistant-specific modification to this integration should be
committed to `ba/brewassistant-rapt-cloud-link` and documented here in the
same change.
