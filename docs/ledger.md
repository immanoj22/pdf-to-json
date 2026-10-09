# Token ledger

Every native token occurrence belongs to a node that references its source spans,
or to an explicit TrimBox discard. The store preserves raw and NFKC text.
The gate checks occurrence identity, reconstructed node content and case-sensitive
Unicode Counter multisets using [\p{L}\p{M}\p{N}]+.

This regex covers letters, marks and numbers from all scripts. It does not assume
Latin text or left-to-right reading order. Script and text direction are optional
evidence; the ledger neither sorts by coordinates nor reverses RTL text.

**CJK without spaces needs a different token rule later.** Under the current
benchmark a contiguous run can count as one token; conservation does not prove
linguistic segmentation or semantic reading order. No CJK tokenizer is implemented
at this gate. The existing Spanish benchmark remains unchanged.
