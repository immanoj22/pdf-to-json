# Gold review backlog

Derived-gold rows found wrong during manual checks. **Gold is never edited**: these rows
wait for a human gold review. Until then the scorer keeps them (and normalises conventions
such as primes, Step 13c gate decision), and reports name them where they affect a number.

## Math gold (OpenStax Statistics, `backend/tests/gold_derived_math/statistics`)

Verified rows (`verified: true`, the 1,254-equation scoring set) that are wrong:

| Slot | Page | Leaf text | What is wrong | Found in |
|---:|---:|---|---|---|
| 1071 | 400 | `x ̄` | the gold box is a calculator icon, not the equation | Step 13a boundary check (tile 19), 13b check |
| 510 | 234 | `6 36` | the gold box is the answer-letter column a–d | Step 13a boundary check (tile 31), 13b check |
| 1549 | 456 | `q ' = 1 – p ' = 1 - 0.278 = 0.722` | two display lines (p′ and q′) merged into one gold row | Step 13a gold check (tile 5) |
| 798 | 340 | `1 m` | holds the numerator only | Step 13a gold check (tile 38) |
| 1388 | 467 | `x ̄` | gold objects lack the overline pieces (the region is exactly x̄) | Step 13b boundary check (tile 9) |
| 1031 | 395 | `X ̄` | gold objects lack the overline pieces (the region is exactly X̄) | Step 13b boundary check (tile 13) |
| 1370 | 465 | `∝ 2` | reference MathML has `∝` (proportional to) where the page shows `α/2` | Step 13c development (failure list) |

Sources: `experiments/out/step13/gold/manual_check_seed14.json`,
`experiments/out/step13/boundaries/manual_check.json`,
`experiments/out/step13b/boundaries/manual_check.json`, `docs/step13c_report.md`.
The manual checks are samples (40 rows each); other wrong verified rows certainly exist (the
Step 13a check estimated verified gold at about 93% correct).

## Book 4 caption gold (Step 12): 84 derived-gold caption misalignments

Medical anatomy (book 4): caption links of the rule "caption region attached to the figure by
the reading order" whose text is a reference figure title or caption, but whose PDF tokens the
derived gold aligned to other units (`para`, or unaligned) on the same page — a gold alignment
error on those tokens, not a converter link error (Step 12 report, limitation 6). Listed from
`experiments/out/step12/links_v4/medical_anatomy_rows.json` (kept links of that rule with
`reference_tag != "caption"` and `text_in_reference_caption`).

| Page | Unit | Gold tag | Caption text |
|---:|---|---|---|
| 43 | `74df2bb882e8` | unaligned | Fig. 1.1C: Developmental anatomy of urinary system. |
| 44 | `49ff2ed51e13` | paragraph | Fig. 1.2B: Living anatomy—palpation—feeling the radial artery pulsations. |
| 44 | `71b7d68fbb4c` | unaligned | Fig. 1.1E: Topographic anatomy of liver. |
| 44 | `b7c948800511` | paragraph | Fig. 1.2A: Living anatomy—inspection—enlarged thyroid gland. |
| 45 | `2b25db84745c` | paragraph | Fig. 1.3: Clinical anatomy—abnormal fetus with meningocele. |
| 45 | `553e9050d83d` | paragraph | Fig. 1.2C: Living anatomy—percussion—thorax for boundaries of heart. |
| 45 | `a5264f7d51c7` | paragraph | Fig. 1.2D: Living anatomy—auscultation— listening to heart beat with stethoscope. |
| 58 | `f1e6486352e5` | unaligned | Fig. 2.1: Levels of organization. |
| 66 | `542ac0641682` | paragraph | Fig. 2.8: Goblet cell. |
| 75 | `092faa3fe733` | unaligned | Fig. 3.1: Skin and appendages. |
| 77 | `4b5d3806915f` | unaligned | Fig. 3.3: Layers of epidermis—microscopic structure. |
| 84 | `4a5e350b85c2` | unaligned | Fig. 3.13: Skin and superficial fascia. |
| 85 | `338cd7671dc0` | unaligned | Fig. 3.14: Intermuscular septum. |
| 87 | `014477218930` | unaligned | Fig. 3.16: Serous cavities of the body. |
| 97 | `29cb654b3f7e` | unaligned | Fig. 4.4: Parts of a long bone. |
| 97 | `2a79a0aa6553` | unaligned | Fig. 4.5: Sagittal section of an adult femur. |
| 98 | `bfebbb691e93` | unaligned | Fig. 4.6: Types of epiphyses. |
| 99 | `32c49321ecff` | unaligned | Fig. 4.8: Blood supply of a long bone. |
| 103 | `dbb8bc412d67` | paragraph | Fig. 4.10: Formation of lamellar bone. |
| 104 | `bd8a2b410caa` | paragraph | Fig. 4.11B: Longitudinal section of compact bone. |
| 104 | `e93ee95f7ab4` | paragraph | Fig. 4.11A: Transverse section of compact bone. |
| 107 | `2361ba9dc194` | unaligned | Fig. 4.13: Morphological classification of bones. |
| 110 | `a4d9eb5d864e` | paragraph | Fig. 4.14: Direction of nutrient foramen in a long bone. |
| 121 | `e4a003df159e` | unaligned | Fig. 5.3: Parts of muscle (biceps). |
| 122 | `9ab96c2d2065` | paragraph | Fig. 5.4: Myotendinous junction showing “dove-tail” appearance. |
| 127 | `7112132472d1` | unaligned | Fig. 5.8: Mechanism of contraction of skeletal muscle. |
| 128 | `9934cda93f6d` | unaligned | Fig. 5.10: Motor unit. |
| 129 | `c560eabb0f37` | unaligned | Fig. 5.11: Neuromuscular junction. |
| 133 | `985fc26d6786` | paragraph | Fig. 5.13: Classification of muscles according to direction of muscle fibers. |
| 146 | `909b05bf725a` | unaligned | Fig. 6.4: Fibrous joint—gomphosis. |
| 147 | `3a44b459e9d7` | unaligned | Fig. 6.6: Cartilaginous (primary) joint— synchondroses. |
| 158 | `6efc15280b15` | unaligned | Fig. 6.11: Axes of movement in a joint. |
| 161 | `3b3f8d27b840` | unaligned | Fig. 6.17: Shoulder—circumduction movement. |
| 161 | `c17846b8c3dc` | unaligned | Fig. 6.18: Thumb—opposition movement. |
| 162 | `ef9e64964555` | unaligned | Fig. 6.20: Hilton’s law. |
| 167 | `8d8758ab74e9` | paragraph | Fig. 7.1: Heart—chambers and major blood vessels connected to heart. |
| 168 | `2d80f57906c1` | paragraph | Fig. 7.2: Different types of blood vessels. |
| 169 | `f293816ac1bd` | unaligned | Fig. 7.3: Large artery. |
| 170 | `1452e5814d7c` | unaligned | Fig. 7.5: Venous valves. |
| 172 | `1dc7c9dbf4ce` | unaligned | Fig. 7.6: Blood circulation—types. |
| 175 | `1530fb893375` | unaligned | Fig. 7.8: Venae comitantes. |
| 176 | `75d9010badff` | unaligned | Fig. 7.9: Interarterial anastomosis. |
| 177 | `ee1ff1c07d54` | unaligned | Fig. 7.11: Arteriovenous anastomosis. |
| 185 | `4949e864ff58` | paragraph | Fig. 8.1: Lymphatic system and lymph flow. |
| 191 | `3b2b5463f0ee` | unaligned | Fig. 8.3: Lymphatic tissue. |
| 199 | `c8f0fccac2a2` | unaligned | Fig. 9.1: Divisions of nervous system. |
| 201 | `b532520e222e` | unaligned | Fig. 9.2: Structure of neuron. |
| 204 | `3845fefd2f6e` | paragraph | Fig. 9.5: Autonomic neurons. |
| 205 | `de77028f1930` | unaligned | Fig. 9.6: Structure of synapse. |
| 206 | `a8b6c57364b6` | paragraph | Fig. 9.7: Classification of synapse. |
| 208 | `2a3f8ce151f2` | unaligned | Fig. 9.10: Spinal cord. |
| 214 | `05b7a16cc92c` | unaligned | Fig. 9.14: Reflex arc. |
| 215 | `70b752198378` | unaligned | Fig. 9.15: Neurovascular bundle. |
| 218 | `aebf7bb6b0d5` | unaligned | Fig. 9.18: Peripheral nerve—coverings. |
| 228 | `d12f6d3b38d4` | unaligned | Fig. 10.3: Pharynx—subdivisions. |
| 229 | `0c2791421032` | unaligned | Fig. 10.6: Larynx—cavity. |
| 229 | `c983fda7e4a8` | unaligned | Fig. 10.5: Larynx—cartilages. |
| 232 | `60ab9568398d` | unaligned | Fig. 10.9: Mouth—parts. |
| 233 | `737412e92a9b` | unaligned | Fig. 10.11: Stomach—parts. |
| 234 | `112fd19de4d4` | unaligned | Fig. 10.12: Duodenum and pancreas. |
| 237 | `e991be5bdb97` | unaligned | Fig. 10.15: Urinary system—parts. |
| 238 | `fbe0569267dd` | unaligned | Fig. 10.16: Urinary bladder. |
| 239 | `926063025764` | unaligned | Fig. 10.17: Male reproductive system. |
| 241 | `1001e8775f2a` | unaligned | Fig. 10.19: Endocrine system. |
| 250 | `89cd913d7203` | paragraph | Fig. 11.4: X-ray—head and neck—lateral view. |
| 250 | `d8b9f33734e2` | paragraph | Fig. 11.3: General features of a long bone of adult. |
| 252 | `b2be20393c2a` | unaligned | Fig. 11.6: Plain X-ray young bone—epiphyseal cartilage. |
| 265 | `75881e7af553` | unaligned | Fig. 12.2: Axillary lines. |
| 267 | `ee63845e5db0` | unaligned | Fig. 12.5: Important skin incisions. |
| 277 | `15475705367e` | unaligned | Fig. 13.5: Muscular fascia. |
| 277 | `86619dd37395` | unaligned | Fig. 13.4: Deep fascia. |
| 277 | `b0ba804faa8e` | unaligned | Fig. 13.3: Superficial fascia. |
| 278 | `3c3af9817ed3` | unaligned | Fig. 13.7: Cleaned muscle. |
| 285 | `9d06dfcaad09` | paragraph | Fig. 14.2: Chromosome—structure. |
| 286 | `3f290b9c4010` | paragraph | Fig. 14.3: Chromosome classification–based on centromere position and arm length. |
| 287 | `5bb08fc30ef7` | unaligned | Fig.14.5: Karyotyping—procedure. |
| 288 | `9c74a60cb01b` | unaligned | Fig. 14.6: Karyotype—normal male. |
| 289 | `ddf78c2680a7` | unaligned | Fig. 14.7: Karyotype—normal female. |
| 292 | `d83236e16a12` | unaligned | Fig. 14.10: Down syndrome–karyotype |
| 292 | `fb514f0efb50` | unaligned | Fig. 14.9: Down syndrome–facial features. |
| 294 | `a4c28cd6e7b1` | unaligned | Fig. 14.14: Klinefelter syndrome–karyotype. |
| 294 | `f956bf10a94c` | unaligned | Fig. 14.15: Punnett square. |
| 297 | `195f904d9169` | paragraph | Fig. 14.16: Symbols used in pedigree chart. |
| 297 | `c622e5c22b15` | unaligned | Fig. 14.17: Sample pedigree chart. |

## Table gold (Step 14a)

Reference table markup that does not describe a grid (overlapping cells); the derived table
gold keeps these tables with a `problems` entry and they are left out of structure scoring.
Gold is not edited.

| Book | Gold table | Reference path | Problem |
|---|---:|---|---|
| 2 Immigrant children | 0 | `/book[1]/chapter[3]/section[6]/table[1]` (Table 3.1) | rows 3-5: the second entry names columns `col1`-`col4` after a first entry already in `col1` (should be `col2`-`col5`) |
| 4 Medical anatomy | 27 | `.../section[1]/section[1]/table[2]` | row 19/20: an entry with `morerows` and the next row's entry both name column 1 |
| 4 Medical anatomy | 39 | `/book[1]/chapter[6]/section[6]/section[1]/table[2]` | rows 3/4: as above (`morerows` overlap in column 1) |

Gold location noise (seen in the Statistics detection misses): numbers repeated across
neighbouring tables (for example the interval rows of Tables 2.57-2.59 on PDF page 144) are
sometimes aligned to the wrong table, so a reference segment may hold only a row or two.
