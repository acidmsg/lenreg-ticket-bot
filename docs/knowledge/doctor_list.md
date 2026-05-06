# doctor_list

## CURL

```bash
curl 'https://zdrav.lenreg.ru/api/doctor_list/' \
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
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'sec-ch-ua: "Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Windows"' \
  -H 'sec-gpc: 1' \
  --data-raw 'speciality_form-speciality_id=53061&speciality_form-clinic_id=272&speciality_form-patient_id=2343192&speciality_form-history_id='
```

## Response

```json
{
    "response": [
        {
            "AriaNumber": null,
            "Name": "Каледин Денис Александрович",
            "IdDoc": "25444",
            "CountFreeTicket": 4,
            "LastDate": {
                "year": "2026",
                "day_verbose": "Втр",
                "month": "05",
                "month_verbose": "Май",
                "time": "16:20",
                "iso": "2026-05-19T16:20:00",
                "day": "19"
            },
            "NearestDate": {
                "year": "2026",
                "day_verbose": "Втр",
                "month": "05",
                "month_verbose": "Май",
                "time": "14:40",
                "iso": "2026-05-19T14:40:00",
                "day": "19"
            },
            "CountFreeParticipantIE": 4
        }
    ],
    "success": true,
    "error": {}
}
```
