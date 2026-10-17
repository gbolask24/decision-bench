# T2 hand audit

100 T2 test items drawn with `random.Random("1017:audit").sample` from the test split sorted by id, read on 17 October 2026 against the 18 categories, before any system saw a test item. Only gold labels and the listings were read; no model output on test items. Listing text is not reproduced here (Amazon's text is not redistributed); notes are in our own words.

Result: 80 plainly right; 3 wrong in the dataset (left as they are, as the pre-registration says, and counted against every system alike); 17 where two categories fit. Of those, the five pairs seen at least twice across this audit and the dev pilot are accepted both ways in `T2-accept.json`; pairs seen once are not, so the test does not get easier than the data warrants.

Pilot dev items (T2 and T3, all three systems) pointed the same way: Plugs filed for a power adaptor and a locking receptacle, and Cords, Adapters & Multi-Outlets for an RCA connector.

Near-empty listings: nine T2 test products have under 30 characters of text; three cannot be placed from text at all. They are kept, since removing them would reshuffle T2 and T3 and the Opus sample, and they cost every system the same.

| # | Item | Gold | Verdict | Note |
|---|---|---|---|---|
| 1 | T2-B00XWJ56KA | Wall Plates & Accessories | ok |  |
| 2 | T2-B08TVSMLVF | Recessed Lighting | ok |  |
| 3 | T2-B003XFVDK0 | Timers | ok |  |
| 4 | T2-B07WGJJLT7 | Switches & Dimmers | ok |  |
| 5 | T2-B0BJRQMNCQ | Cords, Adapters & Multi-Outlets | ok |  |
| 6 | T2-B09N8Z6VCQ | Wall Plates & Accessories | ok | mounting screws for plates; gold fits |
| 7 | T2-B093CC4T5M | Outlets & Accessories | ok |  |
| 8 | T2-B01IZZ6S20 | Wall Plates & Accessories | ok |  |
| 9 | T2-B0759VMWK9 | Electrical Wire | wrong | a crimping and stripping tool; Tools & Hardware fits, Electrical Wire does not |
| 10 | T2-B00OGL4VTU | Breakers, Load Centers & Fuses | ok |  |
| 11 | T2-B07MLRG9GF | Testers | ok |  |
| 12 | T2-B0050T2LR6 | Switches & Dimmers | both | an occupancy sensor switch: Switches & Dimmers or Home Automation Devices |
| 13 | T2-B07Q1BLXT6 | Recessed Lighting | ok |  |
| 14 | T2-B0009DTDZG | Tools & Hardware | ok |  |
| 15 | T2-B001ALK97C | Electrical Wire | ok |  |
| 16 | T2-B000UHLV06 | Recessed Lighting | ok |  |
| 17 | T2-B003Z6PGCI | Cords, Adapters & Multi-Outlets | ok |  |
| 18 | T2-B099YSFZ17 | Breakers, Load Centers & Fuses | ok |  |
| 19 | T2-B0B2KYCM1N | Breakers, Load Centers & Fuses | ok |  |
| 20 | T2-B00JR5CG88 | Electric Motors | wrong | brass rods for a model helicopter; no category fits |
| 21 | T2-B00NO42G3I | Wall Plates & Accessories | both | a box cover: Wall Plates & Accessories or Electrical Boxes, Conduits & Fittings |
| 22 | T2-B000KH9T64 | Electrical Boxes, Conduits & Fittings | wrong | a microphone gooseneck; not an electrical box or fitting |
| 23 | T2-B081L3TSGQ | Cords, Adapters & Multi-Outlets | both | a plug adapter: Cords, Adapters & Multi-Outlets or Plugs |
| 24 | T2-B00673HLE2 | Wall Plates & Accessories | ok |  |
| 25 | T2-B0BRB149VX | Testers | ok |  |
| 26 | T2-B0BZSVPWN8 | Cords, Adapters & Multi-Outlets | ok |  |
| 27 | T2-B000FK9WMC | Electrical Boxes, Conduits & Fittings | both | a box cover: Electrical Boxes, Conduits & Fittings or Wall Plates & Accessories |
| 28 | T2-B0BVYTXLH1 | Light Sockets | ok |  |
| 29 | T2-B07FCW9BG3 | Door Chimes & Bells | ok |  |
| 30 | T2-B01N9Q9DJD | Electric Motors | ok |  |
| 31 | T2-B00XQDBAL6 | Light Sockets | ok |  |
| 32 | T2-B07S2JP9Z1 | Door Chimes & Bells | ok |  |
| 33 | T2-B06XBQD2JH | Wall Plates & Accessories | ok |  |
| 34 | T2-B00FDP5TA8 | Door Chimes & Bells | ok |  |
| 35 | T2-B08VD33Q3D | Testers | ok |  |
| 36 | T2-B08XQ22F47 | Electric Motors | ok |  |
| 37 | T2-B0768WQJQC | Testers | ok |  |
| 38 | T2-B091GTVVLV | Door Chimes & Bells | ok |  |
| 39 | T2-B00U6BTSLK | Wall Plates & Accessories | ok |  |
| 40 | T2-B07GDDHTXG | Plugs | both | a locking female connector: Plugs, Outlets & Accessories or Cords, Adapters & Multi-Outlets |
| 41 | T2-B09GG5CZ61 | Cords, Adapters & Multi-Outlets | both | a rewirable plug: Cords, Adapters & Multi-Outlets or Plugs |
| 42 | T2-B0979VZK6P | Electric Motors | ok |  |
| 43 | T2-B00KLYJS76 | Testers | ok |  |
| 44 | T2-B006HYOCH0 | Wall Plates & Accessories | both | a weatherproof box cover: Wall Plates & Accessories or Electrical Boxes, Conduits & Fittings |
| 45 | T2-B0B3XK9YN2 | Electrical Connectors | ok |  |
| 46 | T2-B09LHQR8KN | Door Chimes & Bells | ok |  |
| 47 | T2-B091BZ8FZD | Electric Motors | ok |  |
| 48 | T2-B09CGQHVKY | Recessed Lighting | ok |  |
| 49 | T2-B071GKCKS3 | Switches & Dimmers | ok |  |
| 50 | T2-B09C8M71WR | Recessed Lighting | ok |  |
| 51 | T2-B001VMX9WM | Electrical Boxes, Conduits & Fittings | ok |  |
| 52 | T2-B072K56RZV | Recessed Lighting | ok |  |
| 53 | T2-B00C9S0U92 | Breakers, Load Centers & Fuses | ok |  |
| 54 | T2-B07D117J6L | Cords, Adapters & Multi-Outlets | both | replacement female plug ends: Cords, Adapters & Multi-Outlets or Plugs |
| 55 | T2-B0BC63QWVV | Door Chimes & Bells | ok |  |
| 56 | T2-B001HU8AF4 | Door Chimes & Bells | ok | solar desk chimes; gold fits the words, barely electrical |
| 57 | T2-B07ZR7S472 | Light Sockets | ok |  |
| 58 | T2-B008UFY8BE | Breakers, Load Centers & Fuses | ok |  |
| 59 | T2-B007D462E4 | Breakers, Load Centers & Fuses | ok |  |
| 60 | T2-B077Y2W984 | Switches & Dimmers | ok |  |
| 61 | T2-B005GDG6AE | Wall Plates & Accessories | ok |  |
| 62 | T2-B07NBMCJ5M | Recessed Lighting | ok |  |
| 63 | T2-B07577GXLR | Testers | ok |  |
| 64 | T2-B003DZJBG8 | Breakers, Load Centers & Fuses | ok | speaker fuse protectors; gold fits |
| 65 | T2-B009MJC1BQ | Breakers, Load Centers & Fuses | ok |  |
| 66 | T2-B000NV77D4 | Plugs | ok |  |
| 67 | T2-B08SWHZ69N | Wall Plates & Accessories | both | outlet gaskets: Wall Plates & Accessories or Outlets & Accessories |
| 68 | T2-B001HK0S04 | Wall Plates & Accessories | ok |  |
| 69 | T2-B01M0J0555 | Wall Plates & Accessories | ok |  |
| 70 | T2-B007R00CMC | Wall Plates & Accessories | ok |  |
| 71 | T2-B01H6W93VG | Cords, Adapters & Multi-Outlets | ok |  |
| 72 | T2-B097DR71G4 | Wall Plates & Accessories | ok |  |
| 73 | T2-B01N3PQ3RW | Switches & Dimmers | ok |  |
| 74 | T2-B091G2L974 | Recessed Lighting | ok |  |
| 75 | T2-B005RU0BNO | Cords, Adapters & Multi-Outlets | ok |  |
| 76 | T2-B0811XS3YP | Recessed Lighting | ok |  |
| 77 | T2-B0000X5DRM | Wall Plates & Accessories | ok |  |
| 78 | T2-B0B8RWBK6S | Door Chimes & Bells | ok |  |
| 79 | T2-B0964WSM55 | Electrical Boxes, Conduits & Fittings | ok |  |
| 80 | T2-B0B5XSQSKN | Door Chimes & Bells | ok |  |
| 81 | T2-B005B0AY0K | Switches & Dimmers | both | a wireless switch kit: Switches & Dimmers or Home Automation Devices |
| 82 | T2-B00C3YDIZA | Outlets & Accessories | both | a weatherproof gasket: Outlets & Accessories or Wall Plates & Accessories |
| 83 | T2-B00LPPBJSG | Breakers, Load Centers & Fuses | ok |  |
| 84 | T2-B008SEW0N0 | Outlets & Accessories | both | a three-gang plate: Outlets & Accessories or Wall Plates & Accessories |
| 85 | T2-B083XCB44F | Outlets & Accessories | ok |  |
| 86 | T2-B000TLSO08 | Electrical Boxes, Conduits & Fittings | ok |  |
| 87 | T2-B004QHE2N4 | Testers | ok |  |
| 88 | T2-B076RLTK7H | Testers | ok |  |
| 89 | T2-B00KLYJS4Y | Testers | ok |  |
| 90 | T2-B005T8FNC8 | Breakers, Load Centers & Fuses | ok |  |
| 91 | T2-B07ZGL7J8P | Recessed Lighting | ok |  |
| 92 | T2-B0CCZS78P9 | Breakers, Load Centers & Fuses | ok |  |
| 93 | T2-B08V1Z58LN | Switches & Dimmers | both | a Wi-Fi dimmer: Switches & Dimmers or Home Automation Devices |
| 94 | T2-B004P7IOFM | Testers | ok |  |
| 95 | T2-B08G7HCWF7 | Light Sockets | ok |  |
| 96 | T2-B001E5Y4YI | Testers | ok |  |
| 97 | T2-B004AH6NPK | Breakers, Load Centers & Fuses | ok |  |
| 98 | T2-B00S9KMHXG | Switches & Dimmers | ok |  |
| 99 | T2-B09VC788ZB | Cords, Adapters & Multi-Outlets | ok |  |
| 100 | T2-B07DPJ4J1J | Switches & Dimmers | both, not accepted | a programmable timer relay: Switches & Dimmers or Timers; seen once |
