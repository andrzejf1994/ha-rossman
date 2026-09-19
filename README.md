# Rossmann — Home Assistant

Unofficial Home Assistant integration for the Polish Rossmann account.

## Features

- Rossmann account login with JWT refresh
- Club card and loyalty points
- Purchase history
- Full Rossmann GO and stationary receipt details
- Today / month / year spend
- Rossmann savings and Rossmann GO savings
- Coupon list
- Manual and automatic coupon activation
- Coupon product catalog service
- Product availability service
- `rossmann_new_purchase` Home Assistant event

## Installation

Copy `custom_components/rossmann` into:

`/config/custom_components/rossmann`

Restart Home Assistant and add **Rossmann** in Settings → Devices & services.

## Important

This integration uses Rossmann's private, undocumented API observed in the official app. It can stop working when Rossmann changes the API.

Your Rossmann password is used only during setup / reauthentication and is not stored by the integration.
