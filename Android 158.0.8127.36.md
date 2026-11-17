# Android 158.0.8127.36

**AAudio per-stream device selection**

Enables per-stream device selection for AAudio streams. No effect on versions of Android prior to Android Q.

`chrome://flags/#aaudio-per-stream-device-selection`

---

**Actor login observation start delay**

Controls how long the actor waits after a login action before it starts waiting for the page to stabilize. Defaults to 3s; Disabled removes the delay.

`chrome://flags/#actor-login-observation-start-delay`

---

**Actor page stability**

Overrides how long the actor waits for the page to stabilize after an action: the minimum wait and the initial and subsequent paint timeouts. Each defaults to 1s.

`chrome://flags/#actor-page-stability`

---

**Actor script tool observation start delay**

Enables observation delay after a script tool action and controls how long the actor waits before it starts waiting for the page to stabilize. Defaults to 0ms when enabled.

`chrome://flags/#actor-script-tool-delay-observation`

---

**Actor type tool observation start delay**

Controls how long the actor waits after a type action before it starts waiting for the page to stabilize. Defaults to 1s; Disabled removes the delay.

`chrome://flags/#actor-type-tool-observation-start-delay`

---

**AI Subscription Avatar Ring follow-up**

Shows the AI subscription avatar decorations on more surfaces. Requires #enable-ai-subscription-avatar-ring.

`chrome://flags/#ai-subscription-avatar-ring-followup`

---

**Android Bookmark Bar Drag Drop**

Enables the Android Bookmark Bar Drag Drop feature.

`chrome://flags/#android-bookmark-bar-drag-drop`

---

**Device model client hint for Desktop Android**

Enables sending the device model in the Sec-CH-UA-Model client hint for users on Desktop Android devices.

`chrome://flags/#android-desktop-ua-model`

---

**Android Tab Search Close Tab Button**

Shows a close button on open tab suggestions in the Android Tab Search overlay, allowing users to close tabs directly from the suggestions list

`chrome://flags/#android-tab-search-close-tab-button`

---

**Android Tab Search Recent Tabs**

Surfaces recent tabs, including tabs from other devices, as suggestions in the Android Tab Search overlay

`chrome://flags/#android-tab-search-recent-tabs`

---

**Disable the locale and country check for Wallet direct offers testing**

Enables testing Wallet direct offers with locales and in countries where they would otherwise be disabled. Requires #autofill-enable-wallet-direct-offers.

`chrome://flags/#autofill-disable-wallet-direct-offers-locale-country-check-for-testing`

---

**Enable Autofill OAuth2 token fix**

When enabled, Autofill payments requests fetch OAuth2 tokens from the identity service on each request, instead of keeping local cache in Autofill components.

`chrome://flags/#autofill-enable-oauth2-token-fix`

---

**Browser controls lockout duration**

Enables lockout duration for Android browser controls on page load and transient shows.

`chrome://flags/#browser-controls-lockout-duration`

---

**Filter Browsing History By Time**

Enables browser history filtering by time.

`chrome://flags/#browsing-history-filter-by-time`

---

**Composebox Persistent AIM Button (Realbox)**

Persists the AIM button in the Realbox Composebox.

`chrome://flags/#composebox-persistent-aim-button-realbox`

---

**Composebox Persistent AIM Button With X**

Shows an X icon on the persistent AIM button. Only effective if the persistent AIM button is also enabled for the surface.

`chrome://flags/#composebox-persistent-aim-button-with-x`

---

**Composebox Personalized Hint Text**

Enable Composebox Personalized Hint Text

`chrome://flags/#composebox-personalized-hint-text`

---

**Composebox Outside Click (Realbox)**

Clicking outside the Realbox Composebox closes the suggestions dropdown and restores page interaction while keeping the Composebox open.

`chrome://flags/#composebox-realbox-outside-click`

---

**Contextual Tasks Side Panel Tab State**

Enables tab-specific contextual tasks side panel state. Clicking links in the side panel opens a new tab instead of focusing an existing tab with the same URL.

`chrome://flags/#contextual-tasks-side-panel-tab-state`

---

**Contextual Tasks Single Tab Menu Item**

Shows the most recent tab as a single menu item above "Add tabs" in the Contextual Tasks tab picker.

`chrome://flags/#contextual-tasks-single-tab-menu-item`

---

**Desktop Android Web App Header App Name**

Shows the installed app's name at the start of the web app window header for TWAs and WebAPKs on desktop Android.

`chrome://flags/#desktop-android-web-app-header-app-name`

---

**Device Trust Connector on Android**

Enables the Device Trust Connector on Android, allowing managed browsers and profiles to share device signals with policy-configured identity providers.

`chrome://flags/#device-trust-connector-android`

---

**Enable payment QR code detection**

When enabled, QR code detection for facilitated payments will be supported on Desktop and Android.

`chrome://flags/#enable-desktop-qr-code-detection`

---

**Text Detection API**

Enables the Web Text Detection API (Shape Detection API for text).

`chrome://flags/#enable-text-detection-api`

---

**Force Drive Disclaimer Accepted**

Whether to force the Google Drive disclaimer to be accepted. This flag is only used for testing purposes.

`chrome://flags/#force-drive-disclaimer-accepted`

---

**Glic actor incremental typing**

When enabled, the Glic actor types text one key at a time with a short delay between keystrokes. When disabled, it dispatches all keystrokes at once.

`chrome://flags/#glic-actor-incremental-typing`

---

**Glic Disable HFCR**

Disables the High Frequency Cookie Rotation frame in Glic.

`chrome://flags/#glic-disable-hfcr`

---

**Lens Send Drive Tab URLs in Composeboxes**

Enables sending Google Drive / Docs tab URLs as unresolved URLs in composeboxes.

`chrome://flags/#lens-send-drive-tab-urls-in-composeboxes`

---

**Lens Use Separate Request ID for Viewport Images**

Enables using separate request IDs for page contents vs page viewport uploads.

`chrome://flags/#lens-use-separate-request-id-for-viewport-images`

---

**Make IdentityManager source of accounts**

Make IdentityManager the source of accounts in Chrome on Android, as opposed to AccountManagerFacade, when this feature is disabled.

`chrome://flags/#make-identity-manager-source-of-accounts`

---

**MediaCodec Block Model Encrypted**

Enables Block Model for MediaCodec on Android for encrypted playback. Has no effect unless MediaCodec Block Model is enabled.

`chrome://flags/#media-codec-block-model-encrypted`

---

**Refresh rate matching for mixed fixed-rate content**

Lowers the display refresh rate when a page only updates fixed-rate content, such as videos, animated images and CSS steps() animations, even if they run at different rates.

`chrome://flags/#mixed-fixed-interval-matcher`

---

**NTP Component Extension**

When enabled, registers the New Tab Page as a component extension.

`chrome://flags/#ntp-component-extension`

---

**Persistent Widget API**

Enables the &lt;persistentwidget&gt; element, which is like an &lt;iframe&gt; but can stay alive without reloading when its opener/embedder navigates from one same-origin document to another.

`chrome://flags/#persistent-widget-api`

---

**Prerender Until Script**

Prerenders pages until a script is about to be executed. The script execution and the page parsing will be deferred until action.

`chrome://flags/#prerender-until-script`

---

**Safe Browsing Temporary No Protection**

Enables temporary 24-hour Safe Browsing opt-out mode with automatic reversion to the previous protection level.

`chrome://flags/#safe-browsing-no-protection-temporary`

---

**Seccomp-BPF GPU sandbox**

Enables the seccomp-bpf filter sandbox for the GPU process on Android.

`chrome://flags/#seccomp-filter-gpu-sandbox`

---

**Settings IA Reorganization**

Enables the reorganized information architecture for Chrome Settings on Android.

`chrome://flags/#settings-ia-reorganization`

---

**Override flyout / drilldown switching logic**

For testing only. Overrides the pointer and screen space switching logic between flyout and drilldown submenus in hierarchical menus.

`chrome://flags/#submenu-type-override`

---

**Tab Group Actions Submenus**

Enables action items and section header in tab group submenus in the app menu.

`chrome://flags/#tab-group-actions-submenus`

---

**Tab group context menu live title update**

Enables live updating of the tab group title on the tab strip as the user types in the context menu title editor.

`chrome://flags/#tab-group-context-menu-live-title-update`

---

**Tab strip link drag and drop**

Enables dragging and dropping links onto the tab strip to open them in a new tab or in an existing tab.

`chrome://flags/#tab-strip-link-drag-drop`

---

**Temporarily unexpire M157 flags.**

Temporarily unexpire flags that expired as of M157. These flags will be removed soon.

`chrome://flags/#temporary-unexpire-flags-m157`

---

**TTC FRE**

Enables the first run experience for TTC.

`chrome://flags/#ttc-fre`

---

**Use passthrough command decoder**

Use chrome passthrough command decoder instead of validating command decoder.

`chrome://flags/#use-passthrough-command-decoder`

---

**WebHID on Desktop Android for extension service workers**

Enables WebHID API support for extension service workers on Desktop Android.

`chrome://flags/#web-hid-on-desktop-android-service-workers`
