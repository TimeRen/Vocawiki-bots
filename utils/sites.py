from pywikibot import Site


def cm():
    return Site(fam="commons", code="commons")


def voca() -> Site:
    return Site(fam="voca", code="voca")


def mirror() -> Site:
    return Site(fam="mirror", code="mirror")


def icu():
    return Site(fam="icu", code="icu")


def icu_cm():
    return Site(fam="icu_cm", code="icu_cm")

def enwp():
    return Site(fam="wikipedia", code="en")


def get_site_by_name(name: str):
    name_to_site = {
        'voca': voca,
        'mirror': mirror,
        'commons': cm
    }
    return name_to_site[name]()
