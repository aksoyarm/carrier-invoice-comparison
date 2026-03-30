# Carrier Invoice Comparison System

## Project Overview
A Streamlit web app that compares carrier (airline/logistics) invoice costs against Navlungo's internal pricing data (QuickSight). Users upload two files:
1. **Carrier Invoice** — an Excel file from one of 5 carriers (UPS, FedEx, THY, PTT, Aramex)
2. **QuickSight Export** — a merged Excel sheet with all Navlungo shipment records (single sheet, mixed carriers)

The system classifies the carrier, extracts waybill/weight/price, applies carrier-specific weight rounding, joins with QuickSight data, and shows a comparison dashboard.

## Tech Stack
- **Python 3.11+**
- **Streamlit** — web UI
- **Pandas** — data processing
- **openpyxl** — Excel parsing

---

## Architecture

### Pipeline Flow
```
Upload Invoice → Classify Carrier → Extract (Key, Weight, Price)
                                          ↓
Upload QuickSight → Parse QS → Join on Waybill ← ─ ─ ─ ┘
                                          ↓
                        Apply Weight Rounding (both sides)
                                          ↓
                        Compare & Display Dashboard
```

---

## 1. Carrier Classification

Classify which carrier an uploaded invoice belongs to. **Do NOT use sheet names** — use content-based detection via a 4-layer cascade. Stop at the first layer that produces a confident result.

### Layer 1 — Header Keyword Matching (primary)
Scan rows 1–2 for header text. Match against unique keyword sets:

```python
HEADER_SIGNATURES = {
    "UPS":    ["Waybill", "Geçerli Ağırlık", "Fatura P.Birimi", "Fatura Tutarı"],
    "FedEx":  ["Billing Country/Territory", "Air Waybill Number", "Rated Weight Amount", "Dim Divisor"],
    "THY":    ["WDC CW", "Dağıtım Noktası", "Konsolide", "HS Code", "Tracking ID"],
    "PTT":    ["BARKOD NO", "GİDİŞ TÜRÜ", "VARIŞ ÜLKESİ", "FATURA NAVLUN"],
    "Aramex": ["Airway Bill No.", "Chargeable Weight", "Pick up Date", "AR Exchange Rate"],
}
```
Score = matched_keywords / total_keywords. If best score ≥ 0.5 → classify.

### Layer 2 — Cell A1 Pattern
- Starts with `"Fatura Detay UPY"` → **UPS**

### Layer 3 — Tracking Number Regex
Sample first tracking value and match:
```
UPS:    ^1Z[A-Z0-9]{16,}
FedEx:  ^\d{12,15}$
THY:    ^33Q6R5\d+
PTT:    ^RE\d{9}TR$
Aramex: ^\d{11}$
```

### Layer 4 — Column Count Heuristic
- \> 80 columns → FedEx (typically 168)
- 18–25 → THY (22)
- 15–22 → Aramex (20)
- 10–15 → UPS (13)
- 8–12 → PTT (11)

If all layers fail → return `"UNKNOWN"` and show user warning.

---

## 2. Column Mapping per Carrier

**Resolution strategy:** First try to find columns by header name regex match. If not found, fall back to column letter index.

### Key (Waybill) Column
| Carrier | Header Name          | Fallback Col |
|---------|----------------------|-------------|
| UPS     | `Waybill`            | A           |
| FedEx   | `Air Waybill Number` | Q           |
| THY     | `Tracking ID`        | B           |
| PTT     | `BARKOD NO`          | B           |
| Aramex  | `Airway Bill No.`    | A           |

### Weight Column
| Carrier | Header Name            | Fallback Col |
|---------|------------------------|-------------|
| UPS     | `Geçerli Ağırlık`     | D           |
| FedEx   | `Rated Weight Amount`  | BK          |
| THY     | `WDC CW`              | H           |
| PTT     | `AĞIRLIK`             | G           |
| Aramex  | `Chargeable Weight`   | I           |

### Price Column
| Carrier | Header Name                  | Fallback Col |
|---------|------------------------------|-------------|
| UPS     | `Tutar`                      | J           |
| FedEx   | `Air Waybill Total Amount`   | BN          |
| THY     | `Tahsil Edilecek Tutar`      | P           |
| PTT     | `FATURA NAVLUN`              | I           |
| Aramex  | `Net Value`                  | L           |

### UPS Special: Header row is Row 2 (Row 1 is a title line like "Fatura Detay UPY...")
### FedEx Special: Values use Turkish number formatting (comma=decimal, dot=thousands). Parse accordingly.

---

## 3. Row Aggregation per Waybill

| Carrier | Grouping   | Weight Aggregation | Price Aggregation |
|---------|------------|-------------------|-------------------|
| UPS     | Multi-row  | First row value   | SUM all rows      |
| FedEx   | Multi-row  | MAX across rows   | SUM all rows      |
| THY     | Single row | Direct value      | Direct value      |
| PTT     | Single row | Direct value      | Direct value      |
| Aramex  | Single row | Direct value      | Direct value      |

---

## 4. Weight Rounding Rules

**CRITICAL: Apply the same rounding rules to BOTH the invoice weight AND the QuickSight `Fatura Ağırlığı` (AC) weight.**

The universal rounding function: `round_up(value, interval)` — always rounds UP to the next interval point. Examples:
- `round_up(0.3, 0.5)` → `0.5`
- `round_up(0.5, 0.5)` → `0.5` (exact match stays)
- `round_up(10.01, 1.0)` → `11.0`
- `round_up(0.11, 0.1)` → `0.2`

### UPS (requires QS `Servis` (Y) column after join)
| Service    | Threshold | Interval |
|------------|-----------|----------|
| express    | < 10 kg   | ↑ 0.5   |
| express    | ≥ 10 kg   | ↑ 1.0   |
| expedited  | any       | ↑ 1.0   |

### FedEx
| Threshold | Interval |
|-----------|----------|
| < 71 kg   | ↑ 0.5   |
| ≥ 71 kg   | ↑ 1.0   |

### THY (evaluate rules in this ORDER — first match wins)

**Rule priority: specific customer rules → general country rules → catch-all**

| Priority | Condition | Threshold | Interval |
|----------|-----------|-----------|----------|
| 1 | Dest = GB variants + QS `Müşteri` (O) = `ops@hiccup.com` | < 5 kg | ↑ 0.5 |
| 1 | Dest = GB variants + QS `Müşteri` (O) = `ops@hiccup.com` | ≥ 5 kg | ↑ 1.0 |
| 2 | Dest = US variants + QS `Müşteri` (O) = `ops@hiccup.com` | < 2.5 kg | ↑ 0.5 |
| 2 | Dest = US variants + QS `Müşteri` (O) = `ops@hiccup.com` | ≥ 2.5 kg | ↑ 1.0 |
| 3 | Dest = AU or US variants (non-hiccup) | < 0.5 kg | ↑ 0.1 |
| 3 | Dest = AU or US variants (non-hiccup) | 0.5–3 kg | ↑ 0.5 |
| 3 | Dest = AU or US variants (non-hiccup) | ≥ 3 kg | ↑ 1.0 |
| 4 | All other destinations | < 10 kg | ↑ 0.5 |
| 4 | All other destinations | ≥ 10 kg | ↑ 1.0 |

**Country matching aliases:**
- US: `US`, `USA`, `United States`, `United States of America`, `AMERİKA`, `AMERIKA`
- GB: `GB`, `UK`, `United Kingdom`, `Great Britain`, `İNGİLTERE`, `INGILTERE`
- AU: `AU`, `Australia`, `AVUSTRALYA`

### PTT
**First:** Convert grams to kg (÷ 1000)
| Threshold (kg) | Interval |
|-----------------|----------|
| < 0.5 kg       | ↑ 0.1   |
| ≥ 0.5 kg       | ↑ 0.5   |

### Aramex
| Threshold | Interval |
|-----------|----------|
| < 10 kg   | ↑ 0.5   |
| ≥ 10 kg   | ↑ 1.0   |

---

## 5. QuickSight Data

### Format
- Single merged sheet, all carriers mixed
- May have a title row in Row 1 (`Express - Sevkiyat Detayları [V2]`) — detect and skip
- Header row contains: `R No`, `Konşimento`, `Taşıyıcı`, `Fatura Ağırlığı`, etc.

### Key Columns
| Field | Header Name | Purpose |
|-------|-------------|---------|
| Waybill (join key) | `Konşimento` (B) | Match with invoice waybill |
| Customer | `Müşteri` (O) | Used for THY hiccup rules |
| Service | `Servis` (Y) | Used for UPS express/expedited |
| Invoice Weight | `Fatura Ağırlığı` (AC) | Weight comparison |
| Customer Price Currency | `Gönderi Bedeli Döviz Cinsi` (AA) | Currency context |
| Customer Price | `Gönderi Bedeli` (AB) | What customer paid Navlungo |
| Shipping Cost Currency | `Sevkiyat Bedeli Döviz Cinsi` (AD) | Currency context |
| Shipping Cost | `Sevkiyat Bedeli` (AE) | Navlungo's cost to carrier |
| DDP Cost | `ddp_bedeli` (AF) | DDP component |
| Shipping Cost Rate | `Sevkiyat Bedeli Kuru` (AG) | Exchange rate used by Navlungo |
| Shipping Cost TL | `Sevkiyat Bedeli TL` (AH) | Shipping cost in TL |
| Payment Date | `Ödeme Tarihi` (AI) | Date used for TCMB rate lookup |
| Carrier | `Taşıyıcı` (X) | Reference only (not used for classification) |

### Number Formatting
QuickSight data may use Turkish locale formatting (comma=decimal, dot=thousands). Handle both formats during parsing. Detect by checking if values contain both dots and commas.

---

## 6. Join & Comparison Logic

### Join
```
invoice_data.waybill → qs_data.Konşimento
```
- Left join from invoice → QS (invoice is the primary dataset)
- Flag unmatched waybills (present in invoice but not in QS, and vice versa)

### Comparison Output per Waybill
| Field | Source |
|-------|--------|
| Waybill | Invoice |
| Carrier | Classified |
| Invoice Weight (raw) | Invoice |
| Invoice Weight (rounded) | Calculated |
| QS Weight (raw) | QS `Fatura Ağırlığı` |
| QS Weight (rounded) | Calculated (same rounding rules) |
| Weight Match | Boolean (rounded invoice == rounded QS) |
| Weight Difference | rounded_invoice - rounded_qs |
| Invoice Price | Invoice (aggregated) |
| QS Customer Price | QS `Gönderi Bedeli` |
| QS Shipping Cost | QS `Sevkiyat Bedeli` |
| Margin (Customer - Invoice) | Gönderi Bedeli - Invoice Price |
| Cost Difference (Shipping - Invoice) | Sevkiyat Bedeli - Invoice Price |
| Payment Date | QS `Ödeme Tarihi` |
| Currency | QS `Sevkiyat Bedeli Döviz Cinsi` |
| QS Rate | QS `Sevkiyat Bedeli Kuru` |
| TCMB Rate | Fetched from TCMB API (Forex Selling) |
| Rate Difference | TCMB Rate - QS Rate |

---

## 7. Streamlit Dashboard

### Layout
1. **Sidebar:** File uploaders (Invoice Excel + QuickSight Excel)
2. **Header:** Detected carrier name + confidence
3. **Summary Cards:**
   - Total waybills processed
   - Matched / Unmatched count
   - Weight discrepancy count
   - Total invoice cost vs total QS cost
4. **Detailed Table:** Full comparison table (sortable, filterable)
5. **Discrepancy View:** Filtered view showing only rows with weight or price mismatches
6. **Export:** Download comparison as Excel

### UX Notes
- Show a spinner during classification + processing
- If carrier = UNKNOWN, show warning and stop
- Highlight rows with discrepancies in red/orange
- Currency columns should show the currency code alongside values

---

## 8. Code Organization

```
project/
├── CLAUDE.md
├── app.py                    # Streamlit entry point
├── requirements.txt          # streamlit, pandas, openpyxl
├── src/
│   ├── __init__.py
│   ├── classifier.py         # Carrier classification (4-layer cascade)
│   ├── parser.py             # Invoice parsing + column resolution
│   ├── weight_rounding.py    # All rounding rules per carrier
│   ├── aggregator.py         # Multi-row aggregation (UPS/FedEx)
│   ├── qs_parser.py          # QuickSight data parsing
│   ├── comparator.py         # Join + comparison logic
│   ├── tcmb.py               # TCMB exchange rate fetcher
│   └── utils.py              # Number format handling, helpers
└── tests/
    ├── test_classifier.py
    ├── test_rounding.py
    ├── test_comparator.py
    └── test_tcmb.py
```

---

## 9. Edge Cases to Handle

- **Empty or malformed files:** Show user-friendly error
- **Turkish number formatting:** Detect and convert (`1.004,12` → `1004.12`)
- **UPS title row:** Row 1 is NOT headers — headers are in Row 2
- **QS title row:** Some sheets start with `Express - Sevkiyat Detayları [V2]` in Row 1 — detect and skip to actual header row
- **Whitespace in values:** Strip leading/trailing whitespace from all string values (waybill numbers, column headers)
- **Missing waybills:** Report which invoice waybills weren't found in QS and vice versa
- **Currency mismatch:** Show currency alongside all monetary values — do NOT convert currencies in V1
- **Case-insensitive matching:** Country names, carrier names, customer emails

---

## 10. TCMB Exchange Rate Comparison

Fetches official TCMB (Central Bank of Turkey) Forex Selling rates for comparison with the internal QS rate (`Sevkiyat Bedeli Kuru`). **Display-only** — does NOT affect Revenue After DDP calculations.

### API
- URL pattern: `https://www.tcmb.gov.tr/kurlar/{YYYYMM}/{DDMMYYYY}.xml`
- No authentication required
- Rate type: **Forex Selling (Döviz Satış)**
- Currency determined per row from QS `Sevkiyat Bedeli Döviz Cinsi` (AD)

### Weekend/Holiday Fallback
TCMB does not publish rates on weekends or Turkish holidays. If the payment date returns 404, the system falls back up to 7 days to find the most recent business day's rate.

### Caching
Rates are cached in-memory by date. One API call per unique date retrieves all currencies, so subsequent lookups for different currencies on the same date are instant.

### Special Cases
- TRY/TL currency → returns `1.0` (no API call)
- API failure or unknown currency → returns `None` (shown as blank in dashboard)