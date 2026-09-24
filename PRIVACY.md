## Privacy Policy

This plugin connects Dify to the Hesperan API. The full privacy policy of the Hesperan service is at
https://hesperan.com/legal/privacy. This page summarizes what the plugin itself does with data.

### Data the plugin collects and stores

The plugin does not collect, store or log any user data itself. It keeps no files, no cache and no analytics.
Your Hesperan API key is stored by Dify as a secret credential of the plugin and is only sent to Hesperan.

### Data sent to a third party

When a tool runs, the plugin sends the following to the Hesperan API at `https://api.hesperan.com` (Hesperan,
Germany; the API gateway runs on OVHcloud servers in Germany) over HTTPS, and to no other service:

- your Hesperan API key, as a bearer token;
- the state you pass to the tool (text or JSON), the question and its options, the profile name, and an optional
  idempotency key;
- for Report outcome: the decision ID and the correct answer.

Only send data you are allowed to share with Hesperan. If the state contains personal data, Hesperan processes it
as your processor to compute the answer.

### What Hesperan stores

According to the Hesperan privacy policy and API documentation (https://hesperan.com/docs/profiles): request content (state and questions) is not stored after the answer is
returned. For billing and abuse prevention, Hesperan stores metadata per request (time, API key, number of
questions, decisions or amount charged, status and latency). Decisions made through a decision profile are logged
with the answer, confidence, action, a keyed hash of the input (not the input itself), the idempotency key and any
outcome you report, and are kept for up to 400 days, or deleted earlier with the profile or the account. The model runs
on Runpod (Runpod, Inc., USA) on GPUs that may be located in the USA or the EU; Runpod receives request content only
to compute the answer and keeps a job's input and result for a short time after it completes. Transfers outside the
EU rely on the EU standard contractual clauses.

### Retention and deletion

The plugin retains nothing. For data held by Hesperan, see the retention rules in the Hesperan privacy policy; to
request access or deletion, write to hello@hesperan.com.

### Contact

Hesperan, hello@hesperan.com. Imprint: https://hesperan.com/legal/imprint
