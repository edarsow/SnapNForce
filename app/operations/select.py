# Todo: Consolidate duplicated code using functional programming techniques
from typing import Optional

from sqlmodel import Session, select

from app import orm


# TODO: Figure out good naming pattern.
#  I don't have one right now, so I've just made stuff "private"


def parcel(session, county_parcel_id: str) -> orm.Parcel:
    statement = select(orm.Parcel).where(
        orm.Parcel.parcelidcnty == county_parcel_id, orm.Parcel.deactivatedts == None
    )
    return session.execute(statement).scalar_one()


def parcel_mailing_addresses(session, parcel_key) -> list[orm.ParcelMailingAddress]:
    statement = select(orm.ParcelMailingAddress).where(
        orm.ParcelMailingAddress.parcel_parcelkey == parcel_key,
        orm.ParcelMailingAddress.deactivatedts == None,
    )
    return session.execute(statement).all()


def parcel_mailing_address(
    session, *, parcel_key: int, mailing_address_id: int
) -> orm.ParcelMailingAddress:
    statement = select(orm.ParcelMailingAddress).where(
        orm.ParcelMailingAddress.parcel_parcelkey == parcel_key,
        orm.ParcelMailingAddress.mailingaddress_addressid == mailing_address_id,
        orm.ParcelMailingAddress.deactivatedts == None,
    )
    return session.execute(statement).scalar_one()


def address(session, address_id: int) -> orm.MailingAddress:
    statement = select(orm.MailingAddress).where(
        orm.MailingAddress.addressid == address_id,
        orm.MailingAddress.deactivatedts == None,
    )
    return session.execute(statement).scalar_one()


def _address(
    session, *, street_id: int, number: str, attn: Optional[str], secondary: Optional[str]
) -> orm.MailingAddress:
    statement = select(orm.MailingAddress).where(
        orm.MailingAddress.street_streetid == street_id,
        orm.MailingAddress.bldgno == number,
        orm.MailingAddress.attention == attn,
        orm.MailingAddress.secondary == secondary,
        orm.MailingAddress.deactivatedts == None,
    )
    return session.execute(statement).scalar_one()


def street(session, street_id: int) -> orm.MailingStreet:
    statement = select(orm.MailingStreet).where(
        orm.MailingStreet.streetid == street_id,
        orm.MailingStreet.deactivatedts == None,
    )
    return session.execute(statement).scalar_one()


def _street(
    session, *, city_state_zip_id: int, street_name: str, is_pobox: bool
) -> orm.MailingStreet:
    statement = select(orm.MailingStreet).where(
        orm.MailingStreet.citystatezip_cszipid == city_state_zip_id,
        orm.MailingStreet.name == street_name,
        orm.MailingStreet.pobox == is_pobox,
        orm.MailingStreet.deactivatedts == None,
    )
    return session.execute(statement).scalar_one()


def city_state_zip(session, city_state_zip_id: int) -> orm.MailingCityStateZip:
    statement = select(orm.MailingCityStateZip).where(
        orm.MailingCityStateZip.id == city_state_zip_id,
        orm.MailingCityStateZip.deactivatedts == None,
    )
    return session.execute(statement).scalar_one()


def _city_state_zip(session, *, city: str, state: str, zip_: str) -> orm.MailingCityStateZip:
    statement = select(orm.MailingCityStateZip).where(
        orm.MailingCityStateZip.city == city,
        orm.MailingCityStateZip.state_abbr == state,
        orm.MailingCityStateZip.zip_code == zip_,
        orm.MailingCityStateZip.deactivatedts == None,
    )
    return session.execute(statement).scalar_one()


def human_mailing_address(session, address_id: int) -> orm.HumanMailingAddress:
    statement = select(orm.HumanMailingAddress).where(
        orm.HumanMailingAddress.humanmailing_addressid == address_id,
        orm.HumanMailingAddress.deactivatedts == None,
    )
    return session.execute(statement).scalar_one()


def human(session, human_id: int) -> orm.Human:
    statement = select(orm.Human).where(
        orm.Human.humanid == human_id,
        orm.Human.deactivatedts == None,
    )
    return session.execute(statement).scalar_one()


def _human(session, *, name: str, is_multi_entity: bool) -> orm.Human:
    statement = select(orm.Human).where(
        orm.Human.name == name,
        orm.Human.multihuman == is_multi_entity,
        orm.Human.deactivatedts == None,
    )
    return session.execute(statement).scalar_one()

def parcels_by_municode(session: Session, *, municode):
    statement = select(orm.Parcel).where(
        orm.Parcel.muni_municode == municode
    )
    return session.execute(statement).scalars()