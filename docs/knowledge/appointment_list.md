# appointment_list

## CURL

```bash
curl 'https://zdrav.lenreg.ru/api/appointment_list/' \
  -H 'Accept: */*' \
  -H 'Accept-Language: ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7' \
  -H 'Cache-Control: no-cache' \
  -H 'Connection: keep-alive' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -b 'csrftoken=NOTPROVIDED' \
  -H 'DNT: 1' \
  -H 'Origin: https://zdrav.lenreg.ru' \
  -H 'Pragma: no-cache' \
  -H 'Referer: https://zdrav.lenreg.ru/signup/free/' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/147.0.0.0' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'sec-ch-ua: "Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Windows"' \
  -H 'sec-gpc: 1' \
  --data-raw 'doctor_form-doctor_id=25444&doctor_form-clinic_id=272&doctor_form-patient_id=2343192&doctor_form-history_id=&doctor_form-appointment_type='
```

## Response

```json
{
    "response": {
        "2026-05-19": [
            {
                "date_end": {
                    "year": "2026",
                    "day_verbose": "Втр",
                    "month": "05",
                    "month_verbose": "Май",
                    "time": "15:00",
                    "iso": "2026-05-19T15:00:00",
                    "day": "19"
                },
                "date_start": {
                    "year": "2026",
                    "day_verbose": "Втр",
                    "month": "05",
                    "month_verbose": "Май",
                    "time": "14:40",
                    "iso": "2026-05-19T14:40:00",
                    "day": "19"
                },
                "id": "41814720000"
            },
            {
                "date_end": {
                    "year": "2026",
                    "day_verbose": "Втр",
                    "month": "05",
                    "month_verbose": "Май",
                    "time": "15:20",
                    "iso": "2026-05-19T15:20:00",
                    "day": "19"
                },
                "date_start": {
                    "year": "2026",
                    "day_verbose": "Втр",
                    "month": "05",
                    "month_verbose": "Май",
                    "time": "15:00",
                    "iso": "2026-05-19T15:00:00",
                    "day": "19"
                },
                "id": "41814719000"
            },
            {
                "date_end": {
                    "year": "2026",
                    "day_verbose": "Втр",
                    "month": "05",
                    "month_verbose": "Май",
                    "time": "16:00",
                    "iso": "2026-05-19T16:00:00",
                    "day": "19"
                },
                "date_start": {
                    "year": "2026",
                    "day_verbose": "Втр",
                    "month": "05",
                    "month_verbose": "Май",
                    "time": "15:40",
                    "iso": "2026-05-19T15:40:00",
                    "day": "19"
                },
                "id": "41814717000"
            },
            {
                "date_end": {
                    "year": "2026",
                    "day_verbose": "Втр",
                    "month": "05",
                    "month_verbose": "Май",
                    "time": "17:00",
                    "iso": "2026-05-19T17:00:00",
                    "day": "19"
                },
                "date_start": {
                    "year": "2026",
                    "day_verbose": "Втр",
                    "month": "05",
                    "month_verbose": "Май",
                    "time": "16:20",
                    "iso": "2026-05-19T16:20:00",
                    "day": "19"
                },
                "id": "41814715000"
            }
        ]
    },

## Payload

```json
{
    "doctor_form-doctor_id": "34333",
    "doctor_form-clinic_id": "271",
    "doctor_form-patient_id": "2343192",
    "doctor_form-history_id": "",
    "doctor_form-appointment_type": ""
}
```
