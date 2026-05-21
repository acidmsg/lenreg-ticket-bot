# clinic_list

**Endpoint:** `POST https://zdrav.lenreg.ru/api/clinic_list/`
**Purpose:** Получение списка поликлиник для указанного района (district_id).

## Parameters

| Parameter                   | Type   | Required | Description        |
| --------------------------- | ------ | -------- | ------------------ |
| `district_form-district_id` | string | yes      | ID района (округа) |

## Response

```json
{
  "response": [
    {
      "IdLPU": "271",
      "LpuName": "ГБУЗ ЛО «Всеволожская КМБ» (Всеволожск, ул.Магистральная, д.12)",
      "LPUShortName": "Всеволожская КМБ (Магистральная)"
    },
    {
      "IdLPU": "272",
      "LpuName": "ГБУЗ ЛО «Всеволожская КМБ» (Всеволожск, Колтушское ш., д.20)",
      "LPUShortName": "Всеволожская КМБ (Колтушское)"
    },
    {
      "IdLPU": "403",
      "LpuName": "ГБУЗ ЛО «Всеволожская КМБ» (Всеволожск, больничный пр., д.12)",
      "LPUShortName": "Всеволожская КМБ (Больничный пр.)"
    }
  ],
  "success": true,
  "error": {}
}
```

## Fields

| Field          | Type   | Description                  |
| -------------- | ------ | ---------------------------- |
| `IdLPU`        | string | ID поликлиники               |
| `LpuName`      | string | Полное название поликлиники  |
| `LPUShortName` | string | Краткое название поликлиники |

## CURL

```bash
curl 'https://zdrav.lenreg.ru/api/clinic_list/' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -b 'csrftoken=NOTPROVIDED' \
  -H 'Origin: https://zdrav.lenreg.ru' \
  -H 'Referer: https://zdrav.lenreg.ru/signup/free/' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --data-raw 'district_form-district_id=12'
```
