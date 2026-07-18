# Changelog

## [0.8.0](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.7.2...v0.8.0) (2026-07-18)


### Features

* enforce strict typing and declare platinum quality scale ([110bcc1](https://github.com/comfort-hub/delonghi-comfort-ha/commit/110bcc1027ccabef69395cb2b08a389ac7aa66ff))

## [0.7.2](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.7.1...v0.7.2) (2026-07-18)


### Bug Fixes

* translate command-failure exception and refresh docs ([a5058a0](https://github.com/comfort-hub/delonghi-comfort-ha/commit/a5058a04a31b1f3df74527360bc4e0d164b4f0a5))

## [0.7.1](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.7.0...v0.7.1) (2026-07-18)


### Bug Fixes

* categorise night mode and silent as config ([386c473](https://github.com/comfort-hub/delonghi-comfort-ha/commit/386c473fe53656ade67d1ff4549191bce04ac477))

## [0.7.0](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.6.0...v0.7.0) (2026-07-18)


### ⚠ BREAKING CHANGES

* switch.eco removed; use climate.set_preset_mode (eco).

### Features

* expose Eco as a climate preset instead of a switch ([5c4acb3](https://github.com/comfort-hub/delonghi-comfort-ha/commit/5c4acb3afda5698fd14ca6f6863438d30ef8ec58)), closes [#43](https://github.com/comfort-hub/delonghi-comfort-ha/issues/43)

## [0.6.0](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.5.1...v0.6.0) (2026-07-18)


### ⚠ BREAKING CHANGES

* brightness moves number.* -> select.*; entity_id/unique_id change; use select.select_option.

### Features

* expose LED brightness as a select instead of a number ([cb589c5](https://github.com/comfort-hub/delonghi-comfort-ha/commit/cb589c5b780c7c49dfb9818337f8b387c5b702ee)), closes [#41](https://github.com/comfort-hub/delonghi-comfort-ha/issues/41)


### Bug Fixes

* disable low-value diagnostic sensors by default ([9c9c1ae](https://github.com/comfort-hub/delonghi-comfort-ha/commit/9c9c1ae5e1e9c338e7a138a721f2a85ec2cd372a))
* simplify fault binary sensors to per-category only ([e2ebbe7](https://github.com/comfort-hub/delonghi-comfort-ha/commit/e2ebbe70984a2d7740ca35dc711444d3e25d0fb2))
* stabilise climate hvac_action and lock the setpoint in AUTO ([5c205cf](https://github.com/comfort-hub/delonghi-comfort-ha/commit/5c205cf3bd68942de7a9463191c8c8b6f3d855f2))

## [0.5.1](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.5.0...v0.5.1) (2026-07-18)


### Bug Fixes

* ship in-repo brand assets for HACS validation ([d086c07](https://github.com/comfort-hub/delonghi-comfort-ha/commit/d086c078e7f15863012cf1925c5587bfa7167396))

## [0.5.0](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.4.1...v0.5.0) (2026-07-18)


### Features

* add a cloud-connection diagnostic binary sensor ([9a5ca48](https://github.com/comfort-hub/delonghi-comfort-ha/commit/9a5ca488cf6604c92fdb5d0d064d50bf69cb03f5))

## [0.4.1](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.4.0...v0.4.1) (2026-07-18)


### Bug Fixes

* pin delonghi-comfort 0.3.0 + reauth/control test coverage ([#3](https://github.com/comfort-hub/delonghi-comfort-ha/issues/3), [#13](https://github.com/comfort-hub/delonghi-comfort-ha/issues/13)) ([1b00180](https://github.com/comfort-hub/delonghi-comfort-ha/commit/1b00180d22fdb75db2b01374d7f9cf65456221dd))

## [0.4.0](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.3.0...v0.4.0) (2026-07-18)


### Features

* split alarms + reconfigure flow + quality-scale bronze ([#9](https://github.com/comfort-hub/delonghi-comfort-ha/issues/9), [#12](https://github.com/comfort-hub/delonghi-comfort-ha/issues/12)) ([d04274e](https://github.com/comfort-hub/delonghi-comfort-ha/commit/d04274e44818b0235e7ffa61bf721b87975023d5))

## [0.3.0](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.2.2...v0.3.0) (2026-07-18)


### Features

* add timer telemetry + LAN-IP/firmware/OTA diagnostics ([#11](https://github.com/comfort-hub/delonghi-comfort-ha/issues/11)) ([85db148](https://github.com/comfort-hub/delonghi-comfort-ha/commit/85db148e89f86f2c08db8df8e9963e99a89e78a2))

## [0.2.2](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.2.1...v0.2.2) (2026-07-18)


### Bug Fixes

* respect the device's temperature unit (Fahrenheit support) ([#5](https://github.com/comfort-hub/delonghi-comfort-ha/issues/5)) ([4cabb37](https://github.com/comfort-hub/delonghi-comfort-ha/commit/4cabb373ed733b80bfadd69f61dd20be6144ec86))

## [0.2.1](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.2.0...v0.2.1) (2026-07-18)


### Bug Fixes

* auto-discover the account region across all regions ([#4](https://github.com/comfort-hub/delonghi-comfort-ha/issues/4)) ([a2f5e41](https://github.com/comfort-hub/delonghi-comfort-ha/commit/a2f5e410e9cffb835247f90af7229b1b82ccc2b0))

## [0.2.0](https://github.com/comfort-hub/delonghi-comfort-ha/compare/v0.1.0...v0.2.0) (2026-07-18)


### Features

* add diagnostics platform and expand config-flow tests ([5f594e7](https://github.com/comfort-hub/delonghi-comfort-ha/commit/5f594e78c32324c4f598a9676703b1f4fb684c71))
* expose the on-board weekly schedule as HVACMode.AUTO ([a05651c](https://github.com/comfort-hub/delonghi-comfort-ha/commit/a05651c687c870ae3c90487bf985684d5218849f))


### Bug Fixes

* offline availability, command-error mapping, PARALLEL_UPDATES ([49a0e36](https://github.com/comfort-hub/delonghi-comfort-ha/commit/49a0e366e36ffc7fa9562d488f33eac94deaae15))
