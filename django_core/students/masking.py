"""One national-id mask for pages and the API (decision 44): all but the last four characters hidden."""


def mask_national_id(value):
    value = str(value or '')
    return '******' + value[-4:] if len(value) > 4 else value
