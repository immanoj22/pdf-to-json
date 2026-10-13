# Every changed metric

No metric fields are excluded. See effects.json for the stage and token witnesses.

## spanish_us_history

| Path | Before | After | Reason |
|---|---|---|---|
| `/cache_key_inputs/paragraph_book_key` | `cc1ed99bcf302cff5da366b7055d6d626fdca8d49883c936548c14be594d42f7` | `57bd589d639e4540a6732212099db8a26e8f7bc33d9d6e2df806407f2e161b05` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/cache_key_inputs/structure_decision_key` | `f4133a312886e19aba9fb3fc20fdee58bfee12432b07c5ad39ee0003b0e9b7d7` | `59cb933c99d104103bc7242be04619fd4914e14a2d34f7ee7025dafcef5da3b8` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/gates/paragraph_book_key` | `cc1ed99bcf302cff5da366b7055d6d626fdca8d49883c936548c14be594d42f7` | `57bd589d639e4540a6732212099db8a26e8f7bc33d9d6e2df806407f2e161b05` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/paragraphs/step11_per_page/boundary_f1` | `0.942797` | `0.942767` | Page 724 reference paragraph 832 is split at alfombra,/también: one additional false positive boundary. The existing paragraph stage acts on the credit lines inserted into main flow by reading order after the layout downgrade. |
| `/paragraphs/step11_per_page/boundary_precision` | `0.918497` | `0.91844` | Page 724 reference paragraph 832 is split at alfombra,/también: one additional false positive boundary. The existing paragraph stage acts on the credit lines inserted into main flow by reading order after the layout downgrade. |
| `/paragraphs/step11_per_page/by_kind/paragraph/exact` | `0.898472` | `0.89835` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step11_per_page/by_kind/paragraph/split` | `394` | `395` | Page 724 reference paragraph 832 changes from one piece to two. Reference credit unit 839 changes from three pieces to two, remains split, and offsets the extra piece in split_errors but not in units_split. |
| `/paragraphs/step11_per_page/exact_unit_match` | `0.894927` | `0.894862` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step11_per_page/exact_units` | `13602` | `13601` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step11_per_page/units_split` | `791` | `792` | Page 724 reference paragraph 832 changes from one piece to two. Reference credit unit 839 changes from three pieces to two, remains split, and offsets the extra piece in split_errors but not in units_split. |
| `/paragraphs/step11_with_chains/boundary_f1` | `0.943013` | `0.942982` | Page 724 reference paragraph 832 is split at alfombra,/también: one additional false positive boundary. The existing paragraph stage acts on the credit lines inserted into main flow by reading order after the layout downgrade. |
| `/paragraphs/step11_with_chains/boundary_precision` | `0.919323` | `0.919265` | Page 724 reference paragraph 832 is split at alfombra,/también: one additional false positive boundary. The existing paragraph stage acts on the credit lines inserted into main flow by reading order after the layout downgrade. |
| `/paragraphs/step11_with_chains/by_kind/paragraph/exact` | `0.879913` | `0.879791` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step11_with_chains/by_kind/paragraph/split` | `394` | `395` | Page 724 reference paragraph 832 changes from one piece to two. Reference credit unit 839 changes from three pieces to two, remains split, and offsets the extra piece in split_errors but not in units_split. |
| `/paragraphs/step11_with_chains/exact_unit_match` | `0.885256` | `0.88519` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step11_with_chains/exact_units` | `13455` | `13454` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step11_with_chains/units_split` | `783` | `784` | Page 724 reference paragraph 832 changes from one piece to two. Reference credit unit 839 changes from three pieces to two, remains split, and offsets the extra piece in split_errors but not in units_split. |
| `/paragraphs/step9_per_page/boundary_f1` | `0.898114` | `0.898084` | Page 724 reference paragraph 832 is split at alfombra,/también: one additional false positive boundary. The existing paragraph stage acts on the credit lines inserted into main flow by reading order after the layout downgrade. |
| `/paragraphs/step9_per_page/boundary_precision` | `0.916507` | `0.916444` | Page 724 reference paragraph 832 is split at alfombra,/también: one additional false positive boundary. The existing paragraph stage acts on the credit lines inserted into main flow by reading order after the layout downgrade. |
| `/paragraphs/step9_per_page/by_kind/paragraph/exact` | `0.895803` | `0.895682` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step9_per_page/by_kind/paragraph/split` | `380` | `381` | Page 724 reference paragraph 832 changes from one piece to two. Reference credit unit 839 changes from three pieces to two, remains split, and offsets the extra piece in split_errors but not in units_split. |
| `/paragraphs/step9_per_page/exact_unit_match` | `0.753076` | `0.75301` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step9_per_page/exact_units` | `11446` | `11445` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step9_per_page/units_split` | `1002` | `1003` | Page 724 reference paragraph 832 changes from one piece to two. Reference credit unit 839 changes from three pieces to two, remains split, and offsets the extra piece in split_errors but not in units_split. |
| `/paragraphs/step9_with_chains/boundary_f1` | `0.897423` | `0.897393` | Page 724 reference paragraph 832 is split at alfombra,/también: one additional false positive boundary. The existing paragraph stage acts on the credit lines inserted into main flow by reading order after the layout downgrade. |
| `/paragraphs/step9_with_chains/boundary_precision` | `0.916924` | `0.916861` | Page 724 reference paragraph 832 is split at alfombra,/también: one additional false positive boundary. The existing paragraph stage acts on the credit lines inserted into main flow by reading order after the layout downgrade. |
| `/paragraphs/step9_with_chains/by_kind/paragraph/exact` | `0.877244` | `0.877123` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step9_with_chains/by_kind/paragraph/split` | `380` | `381` | Page 724 reference paragraph 832 changes from one piece to two. Reference credit unit 839 changes from three pieces to two, remains split, and offsets the extra piece in split_errors but not in units_split. |
| `/paragraphs/step9_with_chains/exact_unit_match` | `0.742483` | `0.742417` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step9_with_chains/exact_units` | `11285` | `11284` | Page 724 reference paragraph 832 loses its exact match; deterministic regression. |
| `/paragraphs/step9_with_chains/units_split` | `998` | `999` | Page 724 reference paragraph 832 changes from one piece to two. Reference credit unit 839 changes from three pieces to two, remains split, and offsets the extra piece in split_errors but not in units_split. |
| `/reading_order/anchors_at_boundaries/end/anchors_by_kind/credit` | `0.949868` | `0.949468` | Pages 324, 350 and 361 each lose one correctly anchored credit stream from the scored float denominator when its text enters main flow. No new anchor miss in the four-page comparison; three correct observations are removed. |
| `/reading_order/anchors_at_boundaries/end/float_anchors` | `0.895186` | `0.894994` | Pages 324, 350 and 361 each lose one correctly anchored credit stream from the scored float denominator when its text enters main flow. No new anchor miss in the four-page comparison; three correct observations are removed. |
| `/reading_order/anchors_at_boundaries/end/kendall_tau` | `0.908957` | `0.908958` | The stream majority changes for four reference units on the four edited pages, adding main-flow comparisons. On page 724 the inserted credit splits the quote order and adds two discordant reference-unit pairs; pooled ratios also reflect the added concordant pairs on the other three pages. This is not a uniform gain. |
| `/reading_order/anchors_at_boundaries/end/within_floats` | `0.921773` | `0.921729` | Page 724 credit tokens leave a figure stream: six concordant within-float reference pairs leave the denominator (changed-page subset 41/44 to 35/38). |
| `/reading_order/anchors_at_boundaries/nearest/anchors_by_kind/credit` | `0.949868` | `0.949468` | Pages 324, 350 and 361 each lose one correctly anchored credit stream from the scored float denominator when its text enters main flow. No new anchor miss in the four-page comparison; three correct observations are removed. |
| `/reading_order/anchors_at_boundaries/nearest/float_anchors` | `0.89153` | `0.891331` | Pages 324, 350 and 361 each lose one correctly anchored credit stream from the scored float denominator when its text enters main flow. No new anchor miss in the four-page comparison; three correct observations are removed. |
| `/reading_order/anchors_at_boundaries/nearest/kendall_tau` | `0.908957` | `0.908958` | The stream majority changes for four reference units on the four edited pages, adding main-flow comparisons. On page 724 the inserted credit splits the quote order and adds two discordant reference-unit pairs; pooled ratios also reflect the added concordant pairs on the other three pages. This is not a uniform gain. |
| `/reading_order/anchors_at_boundaries/nearest/within_floats` | `0.921773` | `0.921729` | Page 724 credit tokens leave a figure stream: six concordant within-float reference pairs leave the denominator (changed-page subset 41/44 to 35/38). |
| `/reading_order/step11/anchors_by_kind/credit` | `0.949868` | `0.949468` | Pages 324, 350 and 361 each lose one correctly anchored credit stream from the scored float denominator when its text enters main flow. No new anchor miss in the four-page comparison; three correct observations are removed. |
| `/reading_order/step11/float_anchors` | `0.90067` | `0.900488` | Pages 324, 350 and 361 each lose one correctly anchored credit stream from the scored float denominator when its text enters main flow. No new anchor miss in the four-page comparison; three correct observations are removed. |
| `/reading_order/step11/kendall_tau` | `0.908957` | `0.908958` | The stream majority changes for four reference units on the four edited pages, adding main-flow comparisons. On page 724 the inserted credit splits the quote order and adds two discordant reference-unit pairs; pooled ratios also reflect the added concordant pairs on the other three pages. This is not a uniform gain. |
| `/reading_order/step11/within_floats` | `0.921773` | `0.921729` | Page 724 credit tokens leave a figure stream: six concordant within-float reference pairs leave the denominator (changed-page subset 41/44 to 35/38). |
| `/reading_order/step9/anchors_by_kind/credit` | `0.949868` | `0.949468` | Pages 324, 350 and 361 each lose one correctly anchored credit stream from the scored float denominator when its text enters main flow. No new anchor miss in the four-page comparison; three correct observations are removed. |
| `/reading_order/step9/float_anchors` | `0.90067` | `0.900488` | Pages 324, 350 and 361 each lose one correctly anchored credit stream from the scored float denominator when its text enters main flow. No new anchor miss in the four-page comparison; three correct observations are removed. |
| `/reading_order/step9/kendall_tau` | `0.891362` | `0.891366` | The stream majority changes for four reference units on the four edited pages, adding main-flow comparisons. On page 724 the inserted credit splits the quote order and adds two discordant reference-unit pairs; pooled ratios also reflect the added concordant pairs on the other three pages. This is not a uniform gain. |
| `/reading_order/step9/main_flow` | `0.945681` | `0.945683` | The stream majority changes for four reference units on the four edited pages, adding main-flow comparisons. On page 724 the inserted credit splits the quote order and adds two discordant reference-unit pairs; pooled ratios also reflect the added concordant pairs on the other three pages. This is not a uniform gain. |
| `/reading_order/step9/within_floats` | `0.921773` | `0.921729` | Page 724 credit tokens leave a figure stream: six concordant within-float reference pairs leave the denominator (changed-page subset 41/44 to 35/38). |
| `/seconds` | `413.0` | `331.4` | Measured evaluation duration; separate run with concurrent verification activity. |

## immigrant_children

| Path | Before | After | Reason |
|---|---|---|---|
| `/cache_key_inputs/paragraph_book_key` | `b49a95a4c63ff1044e7035d25e7b86634b493da4278752d210cb6bfa63fc9678` | `a258bc1c842a543b60af8ff1706221d59f6a9c688a3bf10018c7091de7c154ca` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/cache_key_inputs/structure_decision_key` | `ca58cab16e979b475a6c474b11d7f7173175ddcb7076adb76a281c6c5c675296` | `a3c9183f8ee41dfd0166447b40f92ad1c2dd4725332a8aea92b6475c682e9922` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/gates/paragraph_book_key` | `b49a95a4c63ff1044e7035d25e7b86634b493da4278752d210cb6bfa63fc9678` | `a258bc1c842a543b60af8ff1706221d59f6a9c688a3bf10018c7091de7c154ca` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/seconds` | `24.4` | `34.1` | Measured evaluation duration; separate run with concurrent verification activity. |

## art_therapy_index

| Path | Before | After | Reason |
|---|---|---|---|
| `/cache_key_inputs/paragraph_book_key` | `6d10b56919be3f9456ba49257262d5776c9aca4c2fae63e78209d7a67cc21baa` | `03efd3571945b332d28598f8043c85583c3bfe888fc7ebcdd7e4f6a0c5e7d83a` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/cache_key_inputs/structure_decision_key` | `2fc1be56bc449ad9f27f5f36eb019ebc707c5875878230da262857e7c814b9de` | `e9660e1c66ab62a312b884ce49fd130a1c1723620a5052bb41e3616ea158ecd7` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/gates/paragraph_book_key` | `6d10b56919be3f9456ba49257262d5776c9aca4c2fae63e78209d7a67cc21baa` | `03efd3571945b332d28598f8043c85583c3bfe888fc7ebcdd7e4f6a0c5e7d83a` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/seconds` | `6.1` | `9.6` | Measured evaluation duration; separate run with concurrent verification activity. |

## medical_anatomy

| Path | Before | After | Reason |
|---|---|---|---|
| `/cache_key_inputs/paragraph_book_key` | `96c22021c29896091bd576f7cc4591e04bbbf7180592ffc908cc668df302d013` | `040c35160b7828f473f63f67b6058786208665b9c1bc2a6c07d40263f1a495af` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/cache_key_inputs/structure_decision_key` | `4d14ff22d6812ef467c9b06a41eb0874fce1f66d8b8038fe0fc6b24a1b6fdeb2` | `9ce0d54fe836f779f095e48bd15174896e421b543611e123535c1d7e65adb74d` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/gates/paragraph_book_key` | `96c22021c29896091bd576f7cc4591e04bbbf7180592ffc908cc668df302d013` | `040c35160b7828f473f63f67b6058786208665b9c1bc2a6c07d40263f1a495af` | Upstream layout producer changed; downstream keys carry the changed upstream key. |
| `/seconds` | `57.7` | `81.1` | Measured evaluation duration; separate run with concurrent verification activity. |
