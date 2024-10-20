import datetime
import typing as T
from enum import Enum

import polars as pl
from pydantic import BaseModel, Field


class Shop(BaseModel):
    name: str = Field(
        ...,
        title="Name of the shop.",
        examples=["Edeka", "Rewe", "Aldi", "Lidl", "Netto", "dm"],
    )
    date_str: str = Field(
        ..., title="Date of the purchase.", examples=["2021-05-13", "13.5.2021"]
    )
    time_str: str = Field(
        ..., title="Time of the purchase.", examples=["16:46", "16:46:47"]
    )
    total: float = Field(
        ..., title="Total amount of the purchase in Euros.", examples=[12.34, 42]
    )

    @property
    def date(self) -> T.Optional[datetime.date]:
        # case YYYY-MM-DD
        try:
            date = datetime.datetime.strptime(self.date_str, "%Y-%m-%d")
        except ValueError:
            pass
        else:
            return date.date()

        # case DD.MM.YYYY
        try:
            date = datetime.datetime.strptime(self.date_str, "%d.%m.%Y")
        except ValueError:
            pass
        else:
            return date.date()

        return None

    @property
    def time(self) -> T.Optional[datetime.time]:
        # case HH:MM
        try:
            time = datetime.datetime.strptime(self.time_str, "%H:%M")
        except ValueError:
            pass
        else:
            return time.time()

        # case HH:MM:SS
        try:
            time = datetime.datetime.strptime(self.time_str, "%H:%M:%S")
        except ValueError:
            pass
        else:
            return time.time()

        return None


class CategoryEnum(str, Enum):
    # https://www.instacart.com/company/ideas/grocery-list-categories/
    fruits = "Fruits"
    vegetables = "Vegetables"
    canned_good = "Canned goods"
    dairy = "Dairy"
    meat = "Meat"
    seafood = "Fish and seafood"
    deli = "Deli"
    spices = "Spices"
    snacks = "Snacks"
    baked_good = "Bread and baked goods"
    beverages = "Beverages"
    pasta_rice_cereal = "Pasta, rice and cereal"
    frozen_food = "Frozen food"
    personal_care = "Personal care"
    health_care = "Health care"
    household = "Household supplies"
    baby = "Baby care items"
    pet = "Pet care items"


class Item(BaseModel):
    name: str = Field(
        ...,
        title="Name of the item (in German).",
        examples=["G&G Tomatens.1l", "Mini Romanasalat", "G&G Laug Brez"],
    )
    price: float = Field(
        ..., title="Price of the item in Euros.", examples=[1.23, 4.56]
    )
    count: T.Optional[int] = Field(
        default=1,
        title="Number of items purchased. Often only provided in receipts if multiple items of the same type were purchased.",
        examples=[1, 2, 3],
    )
    mass: T.Optional[float] = Field(
        default=None,
        title="Mass of the item in kilograms. Often only provided in receipts for items sold by weight.",
        examples=[0.1, 2.5],
    )
    tax: T.Optional[str] = Field(
        default=None,
        title="Tax rate applied for the items. The tax rate is indicated usually at the end of the line for each item by some symbol. The symbols are usually supermarket chain specific.",
        examples=["A", "B", "AP", "7%", "19%"],
    )
    category: T.Optional[CategoryEnum] = Field(
        default=None,
        title="Category the grocery item likely belongs to given its name.",
    )


class Receipt(BaseModel):
    shop: Shop = Field(..., title="Shop details.")
    items: T.List[Item] = Field(..., title="List of items purchased.")


POLARS_SHOP_SCHEMA = {
    "name": pl.String,
    "date": pl.Date,
    "time": pl.Time,
    "total": pl.Float64,
    "date_str": pl.String,
    "time_str": pl.String,
}


def convert_to_dataframe_shop(
    receipt: Receipt, polars_shop_schema: T.Dict[str, pl.DataType] | None = None
) -> pl.DataFrame:
    if polars_shop_schema is None:
        polars_shop_schema = POLARS_SHOP_SCHEMA

    shop = pl.from_dict(
        {
            "name": [receipt.shop.name],
            "date": [receipt.shop.date],
            "time": [receipt.shop.time],
            "total": [receipt.shop.total],
            "date_str": [receipt.shop.date_str],
            "time_str": [receipt.shop.time_str],
        },
        schema=polars_shop_schema,
    )

    return shop


POLARS_ITEM_SCHEMA = {
    "name": pl.String,
    "price": pl.Float64,
    "count": pl.Int64,
    "mass": pl.Float64,
    "tax": pl.String,
    "category": pl.String,
}


def convert_to_dataframe_items(
    receipt: Receipt, polars_item_schema: T.Dict[str, pl.DataType] | None = None
) -> pl.DataFrame:
    if polars_item_schema is None:
        polars_item_schema = POLARS_ITEM_SCHEMA

    return pl.from_dicts(
        data=[item.model_dump() for item in receipt.items], schema=polars_item_schema
    )


def polars_info_dataframes_to_pydantic(
    shop: pl.DataFrame, items: pl.DataFrame
) -> Receipt:
    shop_dict = shop.to_dicts()[0]
    items_dict = items.to_dicts()
    return Receipt(shop=Shop(**shop_dict), items=[Item(**d) for d in items_dict])
