# Tail gate: ref.pdf and a second reference PDF

Run: references-only job (bibliography = every page, CPU): `book_core run-book ref.pdf --parts parts.json`, then `book_adapters run --profile tail --format tail`.

## ref.pdf (11 pages) against the client's tail.xml

* references: 147 (refcount 147); **identical to tail.xml: 137/147** (gate: at least 137)
* file: pure ASCII True, CRLF True, well-formed XML (ce: prefix declared in memory) True
* every DOI/address (248) in ref-website and every PMID (190) in ref-text: checks "addresses" and "pmids" have 0 violations
* lossless: 0 missing / 0 extra; omitted with a reason: {'running header': 90, 'text outside the reference list': 178}; verdict pass
* the same text through the client's own tool gives the same 137/147 (the tool and this writer are byte-identical on this PDF)

### The 10 references that differ (`-` ours, `+` tail.xml)

The sample rule is "a hyphen at a line end keeps the hyphen" (the client's tool and this writer both follow it); tail.xml differs from it in three ways: it drops the hyphen of `a-` / `chaconine`, `Saavedra-` / `Vélez`, `gentamicin-` / `induced` (refs 30, 69, 109); it keeps a space in `833- 9`, `2670- 6`, `294- 304` (118, 136, 142); and it keeps a trailing full stop in one title (133) and writes the initials `JØ` without the point (146). The other two (46, 94) are titles the printed text does not split (`var. rapifera` contains a full stop; no full stop between the title and `Food Funct`): each is a review item ("title was cut…" / "could not be separated"), correctable in the review card or in Browse.

#### reference 30

```diff
-<ref-titletext-english>Interactive antifungal activity of the glycoalkaloids a-solanine and a-chaconine</ref-titletext-english>
+<ref-titletext-english>Interactive antifungal activity of the glycoalkaloids a-solanine and achaconine</ref-titletext-english>
-<ref-fulltext>Fewell AM, Roddick JG. Interactive antifungal activity of the glycoalkaloids a-solanine and a-chaconine. Phytochemistry 1993; 33: 323-8. [http://dx.doi.org/10.1016/0031-9422(93)85511-O]
-<ce:source-text>Fewell AM, Roddick JG. Interactive antifungal activity of the glycoalkaloids a-solanine and a-chaconine. Phytochemistry 1993; 33: 323-8. [http://dx.doi.org/10.1016/0031-9422(93)85511-
+<ref-fulltext>Fewell AM, Roddick JG. Interactive antifungal activity of the glycoalkaloids a-solanine and achaconine. Phytochemistry 1993; 33: 323-8. [http://dx.doi.org/10.1016/0031-9422(93)85511-O]<
+<ce:source-text>Fewell AM, Roddick JG. Interactive antifungal activity of the glycoalkaloids a-solanine and achaconine. Phytochemistry 1993; 33: 323-8. [http://dx.doi.org/10.1016/0031-9422(93)85511-O
```

#### reference 46

```diff
-<ref-titletext-english>Chemical Variability and Biological Activities of Brassica rapa var</ref-titletext-english>
+<ref-titletext-english>Chemical Variability and Biological Activities of Brassica rapa var. rapifera Parts Essential Oils Depending on Geographic Variation and Extraction Technique</ref-titletext-eng
-<ref-sourcetitle>rapifera Parts Essential Oils Depending on Geographic Variation and Extraction Technique. Chem Biodivers</ref-sourcetitle>
+<ref-sourcetitle>Chem Biodivers</ref-sourcetitle>
-<ref-text>PMID: 28145061</ref-text>
+<ref-text>[PMID: 28145061]</ref-text>
```

#### reference 69

```diff
-<ce:surname>Saavedra-V&#x000E9;lez</ce:surname>
+<ce:surname>SaavedraV&#x000E9;lez</ce:surname>
-<ref-fulltext>Castro-Torres IG, Naranjo-Rodr&#x000ED;guez EB, Dom&#x000ED;nguez-Ort&#x000ED;z MA, Gallegos-Estudillo J, Saavedra-V&#x000E9;lez MV. Antilithiasic and hypolipidaemic effects of Raphanus
-<ce:source-text>Castro-Torres IG, Naranjo-Rodr&#x000ED;guez EB, Dom&#x000ED;nguez-Ort&#x000ED;z MA, Gallegos-Estudillo J, Saavedra-V&#x000E9;lez MV. Antilithiasic and hypolipidaemic effects of Raphan
+<ref-fulltext>Castro-Torres IG, Naranjo-Rodr&#x000ED;guez EB, Dom&#x000ED;nguez-Ort&#x000ED;z MA, Gallegos-Estudillo J, SaavedraV&#x000E9;lez MV. Antilithiasic and hypolipidaemic effects of Raphanus 
+<ce:source-text>Castro-Torres IG, Naranjo-Rodr&#x000ED;guez EB, Dom&#x000ED;nguez-Ort&#x000ED;z MA, Gallegos-Estudillo J, SaavedraV&#x000E9;lez MV. Antilithiasic and hypolipidaemic effects of Raphanu
```

#### reference 94

```diff
+<ref-title>
+<ref-titletext-english>Antiradical, antimicrobial and cytotoxic activities of commercial beetroot pomace</ref-titletext-english>
+</ref-title>
-<ref-sourcetitle>Antiradical, antimicrobial and cytotoxic activities of commercial beetroot pomace Food Funct</ref-sourcetitle>
+<ref-sourcetitle>Food Funct</ref-sourcetitle>
```

#### reference 109

```diff
-<ref-titletext-english>Beetroot (Beta vulgaris L.) extract ameliorates gentamicin-induced nephrotoxicity associated oxidative stress, inflammation, and apoptosis in rodent model</ref-titletext-englis
+<ref-titletext-english>Beetroot (Beta vulgaris L.) extract ameliorates gentamicininduced nephrotoxicity associated oxidative stress, inflammation, and apoptosis in rodent model</ref-titletext-english
-<ref-fulltext>El Gamal AA, AlSaid MS, Raish M, et al. Beetroot (Beta vulgaris L.) extract ameliorates gentamicin-induced nephrotoxicity associated oxidative stress, inflammation, and apoptosis in rod
-<ce:source-text>El Gamal AA, AlSaid MS, Raish M, et al. Beetroot (Beta vulgaris L.) extract ameliorates gentamicin-induced nephrotoxicity associated oxidative stress, inflammation, and apoptosis in r
+<ref-fulltext>El Gamal AA, AlSaid MS, Raish M, et al. Beetroot (Beta vulgaris L.) extract ameliorates gentamicininduced nephrotoxicity associated oxidative stress, inflammation, and apoptosis in rode
+<ce:source-text>El Gamal AA, AlSaid MS, Raish M, et al. Beetroot (Beta vulgaris L.) extract ameliorates gentamicininduced nephrotoxicity associated oxidative stress, inflammation, and apoptosis in ro
```

#### reference 118

```diff
-<ref-fulltext>Zhang H, Chen F, Wang X, Yao HY. Evaluation of antioxidant activity of parsley (Petroselinum crispum) essential oil and identification of its antioxidant constituents. Food Res Int 2006
-<ce:source-text>Zhang H, Chen F, Wang X, Yao HY. Evaluation of antioxidant activity of parsley (Petroselinum crispum) essential oil and identification of its antioxidant constituents. Food Res Int 20
+<ref-fulltext>Zhang H, Chen F, Wang X, Yao HY. Evaluation of antioxidant activity of parsley (Petroselinum crispum) essential oil and identification of its antioxidant constituents. Food Res Int 2006
+<ce:source-text>Zhang H, Chen F, Wang X, Yao HY. Evaluation of antioxidant activity of parsley (Petroselinum crispum) essential oil and identification of its antioxidant constituents. Food Res Int 20
```

#### reference 133

```diff
-<ref-titletext-english>Chemical constituents from fresh tubers of Dioscorea bulbifera</ref-titletext-english>
+<ref-titletext-english>Chemical constituents from fresh tubers of Dioscorea bulbifera.</ref-titletext-english>
```

#### reference 136

```diff
-<ref-fulltext>Tseng SC, Shen TS, Wu CC, et al. Methyl Protodioscin Induces Apoptosis in Human Osteosarcoma Cells by Caspase-Dependent and MAPK Signaling Pathways. J Agric Food Chem 2017; 65(13): 2670
-<ce:source-text>Tseng SC, Shen TS, Wu CC, et al. Methyl Protodioscin Induces Apoptosis in Human Osteosarcoma Cells by Caspase-Dependent and MAPK Signaling Pathways. J Agric Food Chem 2017; 65(13): 26
+<ref-fulltext>Tseng SC, Shen TS, Wu CC, et al. Methyl Protodioscin Induces Apoptosis in Human Osteosarcoma Cells by Caspase-Dependent and MAPK Signaling Pathways. J Agric Food Chem 2017; 65(13): 2670
+<ce:source-text>Tseng SC, Shen TS, Wu CC, et al. Methyl Protodioscin Induces Apoptosis in Human Osteosarcoma Cells by Caspase-Dependent and MAPK Signaling Pathways. J Agric Food Chem 2017; 65(13): 26
```

#### reference 142

```diff
-<ref-fulltext>Spina M, Cuccioloni M, Sparapani L, et al. Comparative evaluation of flavonoid content in assessing quality of wild and cultivated vegetables for human consumption. J Sci Food Agric 200
-<ce:source-text>Spina M, Cuccioloni M, Sparapani L, et al. Comparative evaluation of flavonoid content in assessing quality of wild and cultivated vegetables for human consumption. J Sci Food Agric 2
+<ref-fulltext>Spina M, Cuccioloni M, Sparapani L, et al. Comparative evaluation of flavonoid content in assessing quality of wild and cultivated vegetables for human consumption. J Sci Food Agric 200
+<ce:source-text>Spina M, Cuccioloni M, Sparapani L, et al. Comparative evaluation of flavonoid content in assessing quality of wild and cultivated vegetables for human consumption. J Sci Food Agric 2
```

#### reference 146

```diff
-<ce:initials>J.&#x000D8;.</ce:initials>
+<ce:initials>J&#x000D8;.</ce:initials>
```

## Second reference PDF: "Hypertension in the Young", Bibliography, pages 77-84 of the book (8 pages, `n.` numbering, `Journal. 2018;14:156-61.`; the pages were cut from the read-only book into a scratch PDF)

* references: 112 (refcount 112), numbered 1..N with no gap
* lossless: 0 missing / 0 extra; verdict pass; omitted: {'running header': 15, 'text outside the reference list': 1}
* 26 references are review items (organisations without initials, books, web pages, a title cut at an inner full stop); the others are read by the rules
