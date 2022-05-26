# """ Common functions made from the primitives found in lib"""
# fmt: off
import re
from functools import partial
from typing import Optional

from bs4 import NavigableString, Tag
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session
from sqlmodel.engine.result import ScalarResult

from app import schemas, orm
from app.constants import LinkedObjectRole
from app.operations import ensure, deactivate, link
from app.operations import select
from app.schemas import CogGeneralAndMortgage
from lib import scrape, parse


async def sync_parcel_data(db: Session, parcel_id: str) -> schemas.GeneralAndMortgage:
    _county_data = await get_parcel_data_from_county(parcel_id)
    _cog_tables = get_cog_tables(db, parcel_id)

    out = {
        "general": None,
        "tax": None
    }
    for county, cog, address_and_human_roles in zip(
        (_county_data.general, _county_data.mortgage),
        (_cog_tables.general, _cog_tables.mortgage),
        (LinkedObjectRole.general_roles, LinkedObjectRole.mortgage_roles),
    ):
        out[address_and_human_roles] = _sync_owner_and_mailing(db, county, cog, address_and_human_roles)
    return schemas.GeneralAndMortgage(
        general=out[LinkedObjectRole.general_roles],
        mortgage=out[LinkedObjectRole.mortgage_roles]
    )


def _sync_owner_and_mailing(
        db,
        county_data: schemas.OwnerAndMailing,
        cog_tables: Optional[schemas.CogTables],
        address_and_human_roles: tuple[int, int]
) -> schemas.OwnerAndMailing:
    address_role, addressee_role = address_and_human_roles
    cog_data = _cog_tables_to_owner_and_mailing(cog_tables)

    # Todo: ensure parcel here
    #  Note: make sure to change references to cog_tables.parcel.parcelkey
    #  to the yet-to-be-created parcel_table.parcelkey

    # Todo: I don't like how this can be reassigned by the following if clause.
    #  Make it pretty and clean.
    address_id = cog_tables and cog_tables.address and cog_tables.address.addressid
    returned_address = county_data.mailing
    same_address = county_data.mailing == cog_data.mailing
    if not same_address:
        if not cog_tables is None:
            # Deactivate address and linked tables
            # TODO: Automatic database cascade
            if cog_tables.parcel_address:
                deactivate.parcel_to_address(db, id=cog_tables.parcel_address.linkid)
            if cog_tables.human_address:
                deactivate.human_to_address(db, id=cog_tables.human_address.linkid)
            if cog_tables.address:
                deactivate.address(db, id=cog_tables.address.addressid)

        # Insert new data
        city_state_zip_table = ensure.city_state_zip(db, city=county_data.mailing.last.city, state=county_data.mailing.last.state, zip_=county_data.mailing.last.zip)
        street_table = ensure.street(db, city_state_zip_id=city_state_zip_table.id, street_name=county_data.mailing.delivery.street, is_pobox=county_data.mailing.delivery.is_pobox)
        address_table = ensure.address(db, street_id=street_table.streetid, number=county_data.mailing.delivery.number,  attn=county_data.mailing.delivery.attn, secondary=county_data.mailing.delivery.secondary)
        # Hmm, should linking go here? Or is it a separate step?
        link.parcel_to_address(db, parcelkey=cog_tables.parcel.parcelkey, address_id=address_table.addressid, role=address_role)
        address_id = address_table.addressid
        returned_address = schemas.Mailing(
            delivery=schemas.DeliveryAddressLine(
                is_pobox=street_table.pobox,
                attn=address_table.attention,
                number=address_table.bldgno,
                street=street_table.name,
                secondary=address_table.secondary,
            ),
            last=schemas.LastLine(
                city=city_state_zip_table.city,
                state=city_state_zip_table.state_abbr,
                zip=city_state_zip_table.zip_code
            )
        )

    human_id = cog_tables and cog_tables.human and cog_tables.human.humanid
    returned_human = county_data.owner
    same_human = county_data.owner == cog_data.owner
    if not same_human:
        if not cog_tables is None:
            if cog_tables.human_parcel:
                deactivate.human_to_parcel(db, id=cog_tables.human_parcel)
            # Todo: If we already deactivated human parcel, we may hit the database an unnecessary time here
            #  At the time of writing, clean code matters more to me than efficiency.
            #  I still would like to remove the unnecessary call
            if cog_tables.human_address:
                deactivate.human_to_address(db, id=cog_tables.human_address.linkid)
            if cog_tables.human:
                deactivate.human(db, id=cog_tables.human.humanid)
        human_table = ensure.human(db, name=county_data.owner.name, is_multi_entity=county_data.owner.is_multi_entity)
        link.human_to_parcel(db, parcelkey=cog_tables.parcel.parcelkey, humanid=human_table.humanid, role=addressee_role)
        human_id = human_table.humanid
        returned_human = schemas.Owner(
            name=human_table.name,
            is_multi_entity=human_table.multihuman
        )

    if (not same_human) or (not same_address):
        link.human_to_address(db, human_id=human_id, address_id=address_id, role=addressee_role)

    return schemas.OwnerAndMailing(
        owner=returned_human,
        mailing=returned_address
    )



def _cog_tables_to_owner_and_mailing(t: schemas.CogTables) -> schemas.OwnerAndMailing:
    # Todo: long-winded ternary statements are not very Pythonic.
    #  Break into actual if / else clauses
    owner = None if (t is None or t.human is None) else schemas.Owner(
            name=t.human.name,
            is_multi_entity=t.human.multihuman
        )
    mailing = None if (t is None or not t.has_address_tables) else schemas.Mailing(
        delivery_line=schemas.DeliveryAddressLine(
            is_pobox=t.street.pobox,
            attn=t.address.attention,
            number=t.address.bldgno,
            street=t.street.name,
            secondary=t.address.secondary,
        ),
        last_line=schemas.LastLine(
            city=t.city_state_zip.city,
            state=t.city_state_zip.state_abbr,
            zip=t.city_state_zip.zip_code
        )
    )
    return schemas.OwnerAndMailing(
        owner=owner,
        mailing=mailing
    )






async def get_parcel_data_from_county(parcel_id: str) -> schemas.GeneralAndMortgage:
    general_data = await get_general_data_from_county(parcel_id)
    tax_data = await get_tax_data_from_county(parcel_id)
    return schemas.GeneralAndMortgage(general=general_data, mortgage=tax_data)


async def get_general_data_from_county(parcel_id: str):
    response = await scrape.general_info(parcel_id)
    response.raise_for_status()
    _owner, _mailing = parse.general_html_content(response.content)
    owner = owner_from_raw(_owner)
    mailing = mailing_from_raw_general(_mailing)
    return schemas.OwnerAndMailing(owner=owner, mailing=mailing)


async def get_tax_data_from_county(parcel_id: str):
    response = await scrape.tax_info(parcel_id)
    response.raise_for_status()
    _owner, _mailing = parse.mortgage_html_content(response.content)
    owner = owner_from_raw(_owner)
    mailing = mailing_from_raw_tax(_mailing)
    return schemas.OwnerAndMailing(owner=owner, mailing=mailing)


def owner_from_raw(data: list[Tag | NavigableString]) -> schemas.Owner:
    owner_list = _clean_tags(data)
    is_multi_entity = False
    if len(owner_list) > 1:
        is_multi_entity = True
    # Owner names often have trailing whitespace
    #  If it isn't stripped away, the dirty_owner != clean_owner check
    #  will always return True.
    dirty_owner = " & ".join(o.strip() for o in owner_list)
    clean_owner = _clean_whitespace(dirty_owner)
    if dirty_owner != clean_owner:  # Todo:
        # Todo: this is most likely duplicate logic,
        #  but I haven't taken time to prove it yet
        is_multi_entity = True
    return schemas.Owner(name=clean_owner, is_multi_entity=is_multi_entity)


def mailing_from_raw_tax(data: list[Tag | NavigableString]) -> Optional[schemas.Mailing]:
    # Todo: these two functions almost certainly belong in lib.parse
    address_list = _clean_tags(data)
    if len(address_list) == 3:
        delivery_line = parse.mortgage_delivery_address_line(address_list[0])
        last_line = parse.mortgage_last_line(city_state=address_list[1], zip=address_list[2])
    elif not address_list:
        return None
    else:
        raise NotImplementedError("I haven't dealt with this yet")
    return schemas.Mailing(delivery=delivery_line, last=last_line)


def mailing_from_raw_general(data: list[Tag | NavigableString]) -> Optional[schemas.Mailing]:
    address_list = _clean_tags(data)
    if len(address_list) == 2:
        delivery_line = parse.general_delivery_address_line(address_list[0])
        last_line = parse.general_city_state_zip(address_list[1])
    elif len(address_list) == 3:
        delivery_line = parse.general_delivery_address_line(address_list[1])
        # "ATTN ", "ATTN: ", "ATTENTION ", "ATTENTION: "
        delivery_line.attn = re.sub(r"ATT(N|ENTION):?\s+", address_list[0], "")
        last_line = parse.general_city_state_zip(address_list[2])
    elif len(address_list) == 0:
        return None
    else:
        raise RuntimeError
    return schemas.Mailing(delivery=delivery_line, last=last_line)


def _clean_tags(content: list[Tag | NavigableString]) -> list[str]:
    return [str(tag) for tag in content if isinstance(tag, NavigableString)]


def _clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def get_cog_tables(db, parcel_id) -> CogGeneralAndMortgage:
    all_addresses = []
    parcel = select.parcel(db, parcel_id)
    if parcel is None:
        return schemas.CogGeneralAndMortgage(general=None, mortgage=None)
    parcel_addresses = select.parcel_mailing_addresses(db, parcel.parcelkey)
    for (parcel_address,) in parcel_addresses:
        address = select.address(db, parcel_address.mailingaddress_addressid)
        street = select.street(db, address.street_streetid)
        city_state_zip = select.city_state_zip(db, street.citystatezip_cszipid)
        try:
            human_address = select.human_mailing_address(db, address.addressid)
            human = select.human(db, human_address.humanmailing_humanid)
        except NoResultFound:
            human_address = human = None
        tables = schemas.CogTables(
            address=address,
            parcel_address=parcel_address,
            street=street,
            city_state_zip=city_state_zip,
            human=human,
            human_address=human_address,
        )
        all_addresses.append(tables)
    # todo: this only works because we are currently lax and accept optional tables
    #  it would be nice to roll this logic into the above code
    general = _match_general(all_addresses) or schemas.CogTables()
    mortgage = _match_mortgage(all_addresses) or schemas.CogTables()
    general.parcel = mortgage.parcel = parcel
    return schemas.CogGeneralAndMortgage(general=general, mortgage=mortgage)


def _match_number(num_to_match: int, owners_and_mailings: list[schemas.CogTables]):
    for x in owners_and_mailings:
        if x.parcel_address.linkedobjectrole_lorid == num_to_match:
            return x
    return None


_match_general = partial(_match_number, LinkedObjectRole.GENERAL_HUMAN_MAILING_ADDRESS)
_match_mortgage = partial(_match_number, LinkedObjectRole.MORTGAGE_HUMAN_MAILING_ADDRESS)


def select_all_parcels_in_municode(db: Session, *, municode: int):
    return select.parcels_by_municode(db, municode=municode)
