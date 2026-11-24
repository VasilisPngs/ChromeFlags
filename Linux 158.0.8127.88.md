# Linux 158.0.8127.88

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

**Disable the locale and country check for Wallet direct offers testing**

Enables testing Wallet direct offers with locales and in countries where they would otherwise be disabled. Requires #autofill-enable-wallet-direct-offers.

`chrome://flags/#autofill-disable-wallet-direct-offers-locale-country-check-for-testing`

---

**Enable Autofill OAuth2 token fix**

When enabled, Autofill payments requests fetch OAuth2 tokens from the identity service on each request, instead of keeping local cache in Autofill components.

`chrome://flags/#autofill-enable-oauth2-token-fix`

---

**Enable Wallet Gmail offers**

When enabled, offers from Gmail are synced via Google Wallet in addition to direct offers.

`chrome://flags/#autofill-enable-wallet-gmail-offers`

---

**BackForwardCache for component extension frames**

Allows pages embedding opted-in component extension frames to enter BackForwardCache.

`chrome://flags/#back-forward-cache-for-component-extension-frames`

---

**Filter Browsing History By Time**

Enables browser history filtering by time.

`chrome://flags/#browsing-history-filter-by-time`

---

**Multi-Token Prediction (MTP) for Built-in AI**

Enables Multi-Token Prediction (MTP) speculative decoding for Built-in AI APIs. Also enables requisite Gemma 4 and Sampling Mode features. Summarizer API sessions automatically use greedy sampling with MTP by default. Prompt API sessions use MTP when greedy sampling options are specified (such as samplingMode: "most-predictable"); default and non-greedy sessions run with standard decoding.

`chrome://flags/#built-in-ai-mtp`

---

**Contextual Tasks Ephemeral Pin Button Refactor**

Routes the unpinned Contextual Tasks ephemeral toolbar button through PinnedToolbarActions in Pinning V2 instead of ContextualTasksButton.

`chrome://flags/#contextual-tasks-ephemeral-pin-button-refactor`

---

**Contextual Tasks Pinned Button Active Indicator**

Highlights the permanent pinned contextual tasks toolbar button in blue with an underline indicator when the active tab has an ongoing thread or session.

`chrome://flags/#contextual-tasks-pinned-button-active-indicator`

---

**Contextual Tasks Pinning String Variants**

Selects the user-facing string variant ('Google Search AI Mode', 'Google Search side panel', 'Google Search in side panel', 'Google Search in Chrome', or 'Google Search panel') used across Contextual Tasks pinning, tooltips, IPH, and tutorial strings.

`chrome://flags/#contextual-tasks-pinning-string-variants`

---

**Contextual Tasks Pinning V2**

Consolidates the pinning and ephemeral toolbar buttons for the new right-hand Search in Chrome (SiC) side panel.

`chrome://flags/#contextual-tasks-pinning-v2`

---

**Contextual Tasks Side Panel Tab State**

Enables tab-specific contextual tasks side panel state. Clicking links in the side panel opens a new tab instead of focusing an existing tab with the same URL.

`chrome://flags/#contextual-tasks-side-panel-tab-state`

---

**Contextual Tasks Single Tab Menu Item**

Shows the most recent tab as a single menu item above "Add tabs" in the Contextual Tasks tab picker.

`chrome://flags/#contextual-tasks-single-tab-menu-item`

---

**Unify SIC Pin Button Logos**

Unifies the logo (Spark, Super G, or Gray Super G) used across the Contextual Tasks (Search in Chrome) permanent toolbar and ephemeral pin buttons.

`chrome://flags/#contextual-tasks-unify-pin-button-logos`

---

**Enable new tab page browser feature suggestions**

Shows suggestions to explore browser capabilities (eg. signing in) on the new tab page.

`chrome://flags/#enable-ntp-browser-promos`

---

**Text Detection API**

Enables the Web Text Detection API (Shape Detection API for text).

`chrome://flags/#enable-text-detection-api`

---

**GEiC first-run experience**

Enables the Gemini Enterprise in Chrome (GEiC) first-run experience. Requires GEiC to be enabled.

`chrome://flags/#geic-fre`

---

**GEiC guest URL**

Configures the guest URL loaded into the Gemini Enterprise in Chrome (GEiC) side panel.

`chrome://flags/#geic-guest-url`

---

**Glic actor incremental typing**

When enabled, the Glic actor types text one key at a time with a short delay between keystrokes. When disabled, it dispatches all keystrokes at once.

`chrome://flags/#glic-actor-incremental-typing`

---

**Glic Disable HFCR**

Disables the High Frequency Cookie Rotation frame in Glic.

`chrome://flags/#glic-disable-hfcr`

---

**Glic Experimental Triggering OS Notification**

Enables OS-level system notifications for Glic experimental triggering task starts when no browser window is active.

`chrome://flags/#glic-experimental-triggering-os-notification`

---

**Glic Show, not Tell Tutorials**

Enables Show, not Tell Tutorials in Gemini in Chrome.

`chrome://flags/#glic-show-not-tell-tutorials`

---

**InfoBar queued count pill**

Shows a "+N" count pill in the bottom-most InfoBar while lower-priority InfoBars wait in the prioritization queue.

`chrome://flags/#infobar-queued-count-pill`

---

**Lens Send Drive Tab URLs in Composeboxes**

Enables sending Google Drive / Docs tab URLs as unresolved URLs in composeboxes.

`chrome://flags/#lens-send-drive-tab-urls-in-composeboxes`

---

**Lens Use Separate Request ID for Viewport Images**

Enables using separate request IDs for page contents vs page viewport uploads.

`chrome://flags/#lens-use-separate-request-id-for-viewport-images`

---

**Media capture element preview**

Enables camera and microphone preview for &lt;camera&gt;, &lt;microphone&gt;, and &lt;usermedia&gt; elements.

`chrome://flags/#media-capture-element-preview`

---

**NTP Component Extension**

When enabled, registers the New Tab Page as a component extension.

`chrome://flags/#ntp-component-extension`

---

**Page Colors settings**

When enabled, shows a Page Colors control in Chrome's accessibility settings, which lets users pick a high contrast theme for web content or turn forced colors off, independently of the operating system theme.

`chrome://flags/#page-colors-settings`

---

**Password sign-in in-context Trusted Vault error resolution**

Enables resolution of Trusted Vault encryption errors directly within the sign-in autofill dropdown.

`chrome://flags/#password-sign-in-in-context-error-resolution`

---

**Payment Handler Custom Size**

Lets a payment app customize the size of its Payment Handler window statically through the preferredSize option of PaymentRequestEvent.openWindow() and/or dynamically at runtime through window.resizeTo().

`chrome://flags/#payment-handler-custom-size`

---

**Persistent Widget API**

Enables the &lt;persistentwidget&gt; element, which is like an &lt;iframe&gt; but can stay alive without reloading when its opener/embedder navigates from one same-origin document to another.

`chrome://flags/#persistent-widget-api`

---

**Prerender Until Script**

Prerenders pages until a script is about to be executed. The script execution and the page parsing will be deferred until action.

`chrome://flags/#prerender-until-script`

---

**Reading Mode Send Feedback**

Enables the send feedback entry point in the Reading Mode settings menu.

`chrome://flags/#read-anything-send-feedback`

---

**Safe Browsing Temporary No Protection**

Enables temporary 24-hour Safe Browsing opt-out mode with automatic reversion to the previous protection level.

`chrome://flags/#safe-browsing-no-protection-temporary`

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
