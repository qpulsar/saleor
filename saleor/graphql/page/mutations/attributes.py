from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List

import graphene
from django.core.exceptions import ValidationError

from ....core.permissions import PageTypePermissions
from ....page.error_codes import PageErrorCode
from ....product import AttributeType, models
from ...core.mutations import BaseMutation
from ...core.types.common import PageError
from ...page.types import PageType
from ...product.types import Attribute
from ...utils import resolve_global_ids_to_primary_keys

if TYPE_CHECKING:
    from ....page import models as page_models


class PageAttributeAssign(BaseMutation):
    page_type = graphene.Field(PageType, description="The updated page type.")

    class Arguments:
        page_type_id = graphene.ID(
            required=True,
            description="ID of the page type to assign the attributes into.",
        )
        attribute_ids = graphene.List(
            graphene.NonNull(graphene.ID),
            required=True,
            description="The IDs of the attributes to assign.",
        )

    class Meta:
        description = "Assign attributes to a given page type."
        error_type_class = PageError
        error_type_field = "page_errors"
        permissions = (PageTypePermissions.MANAGE_PAGE_TYPES_AND_ATTRIBUTES,)

    @classmethod
    def clean_attributes(
        cls,
        errors: Dict["str", List[ValidationError]],
        page_type: "page_models.PageType",
        attr_pks: List[int],
    ):
        """Ensure the attributes are page attributes and are not already assigned."""

        # check if any attribute is not a page type
        invalid_attributes = models.Attribute.objects.filter(pk__in=attr_pks).exclude(
            type=AttributeType.PAGE_TYPE
        )

        if invalid_attributes:
            invalid_attributes_ids = [
                graphene.Node.to_global_id("Attribute", attr.pk)
                for attr in invalid_attributes
            ]
            error = ValidationError(
                "Only page attributes can be assigned.",
                code=PageErrorCode.INVALID.value,
                params={"attributes": invalid_attributes_ids},
            )
            errors["attribute_ids"].append(error)

        # check if any attribute is already assigned to this page type
        assigned_attrs = models.Attribute.objects.get_assigned_page_type_attributes(
            page_type.pk
        ).filter(pk__in=attr_pks)

        if assigned_attrs:
            assigned_attributes_ids = [
                graphene.Node.to_global_id("Attribute", attr.pk)
                for attr in assigned_attrs
            ]
            error = ValidationError(
                "Some of the attributes have been already assigned to this page type.",
                code=PageErrorCode.ATTRIBUTE_ALREADY_ASSIGNED.value,
                params={"attributes": assigned_attributes_ids},
            )
            errors["attribute_ids"].append(error)

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        errors = defaultdict(list)
        page_type_id: str = data["page_type_id"]
        attribute_ids = data["attribute_ids"]

        # retrieve the requested page type
        page_type = cls.get_node_or_error(info, page_type_id, only_type=PageType)

        # resolve all passed attributes IDs to attributes pks
        _, attr_pks = resolve_global_ids_to_primary_keys(attribute_ids, Attribute)

        # ensure the attributes are assignable
        cls.clean_attributes(errors, page_type, attr_pks)

        if errors:
            raise ValidationError(errors)

        page_type.page_attributes.add(*attr_pks)

        return cls(page_type=page_type)


class PageAttributeUnassign(BaseMutation):
    page_type = graphene.Field(PageType, description="The updated page type.")

    class Arguments:
        page_type_id = graphene.ID(
            required=True,
            description=(
                "ID of the page type from which the attributes should be unassign."
            ),
        )
        attribute_ids = graphene.List(
            graphene.NonNull(graphene.ID),
            required=True,
            description="The IDs of the attributes to unassign.",
        )

    class Meta:
        description = "Unassign attributes from a given page type."
        permissions = (PageTypePermissions.MANAGE_PAGE_TYPES_AND_ATTRIBUTES,)
        error_type_class = PageError
        error_type_field = "page_errors"

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        page_type_id = data["page_type_id"]
        attribute_ids = data["attribute_ids"]

        # retrieve the requested page type
        page_type = cls.get_node_or_error(info, page_type_id, only_type=PageType)

        # resolve all passed attributes IDs to attributes pks
        _, attr_pks = resolve_global_ids_to_primary_keys(attribute_ids, Attribute)

        page_type.page_attributes.remove(*attr_pks)

        return cls(page_type=page_type)
