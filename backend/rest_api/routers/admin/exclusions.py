"""
Branch exclusion endpoints for category/subcategory management.
"""

from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select,
    joinedload,
    get_db, current_user, Category, Subcategory, Branch,
    BranchCategoryExclusion, BranchSubcategoryExclusion,
    soft_delete, set_created_by,
    get_user_id, get_user_email,
    require_admin,
)
from rest_api.routers.admin_schemas import (
    ExclusionOverview, CategoryExclusionSummary, SubcategoryExclusionSummary,
    ExclusionBulkUpdate,
)


router = APIRouter(tags=["admin-exclusions"])


@router.get("/exclusions", response_model=ExclusionOverview)
def get_exclusions_overview(
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> ExclusionOverview:
    """Get complete overview of all category and subcategory exclusions."""
    tenant_id = user["tenant_id"]

    categories = db.execute(
        select(Category).where(
            Category.tenant_id == tenant_id,
            Category.is_active == True,
        ).order_by(Category.name)
    ).scalars().all()

    cat_exclusions = db.execute(
        select(BranchCategoryExclusion).where(
            BranchCategoryExclusion.tenant_id == tenant_id,
            BranchCategoryExclusion.is_active == True,
        )
    ).scalars().all()

    cat_exclusion_map: dict[int, list[int]] = {}
    for exc in cat_exclusions:
        if exc.category_id not in cat_exclusion_map:
            cat_exclusion_map[exc.category_id] = []
        cat_exclusion_map[exc.category_id].append(exc.branch_id)

    category_summaries = [
        CategoryExclusionSummary(
            category_id=cat.id,
            category_name=cat.name,
            excluded_branch_ids=cat_exclusion_map.get(cat.id, []),
        )
        for cat in categories
    ]

    subcategories = db.execute(
        select(Subcategory).options(
            joinedload(Subcategory.category)
        ).where(
            Subcategory.tenant_id == tenant_id,
            Subcategory.is_active == True,
        ).order_by(Subcategory.name)
    ).scalars().unique().all()

    subcat_exclusions = db.execute(
        select(BranchSubcategoryExclusion).where(
            BranchSubcategoryExclusion.tenant_id == tenant_id,
            BranchSubcategoryExclusion.is_active == True,
        )
    ).scalars().all()

    subcat_exclusion_map: dict[int, list[int]] = {}
    for exc in subcat_exclusions:
        if exc.subcategory_id not in subcat_exclusion_map:
            subcat_exclusion_map[exc.subcategory_id] = []
        subcat_exclusion_map[exc.subcategory_id].append(exc.branch_id)

    subcategory_summaries = [
        SubcategoryExclusionSummary(
            subcategory_id=subcat.id,
            subcategory_name=subcat.name,
            category_id=subcat.category_id,
            category_name=subcat.category.name if subcat.category else "Unknown",
            excluded_branch_ids=subcat_exclusion_map.get(subcat.id, []),
        )
        for subcat in subcategories
    ]

    return ExclusionOverview(
        category_exclusions=category_summaries,
        subcategory_exclusions=subcategory_summaries,
    )


@router.get("/exclusions/categories/{category_id}", response_model=CategoryExclusionSummary)
def get_category_exclusions(
    category_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> CategoryExclusionSummary:
    """Get exclusion details for a specific category."""
    category = db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.tenant_id == user["tenant_id"],
            Category.is_active == True,
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    exclusions = db.execute(
        select(BranchCategoryExclusion).where(
            BranchCategoryExclusion.category_id == category_id,
            BranchCategoryExclusion.tenant_id == user["tenant_id"],
            BranchCategoryExclusion.is_active == True,
        )
    ).scalars().all()

    return CategoryExclusionSummary(
        category_id=category.id,
        category_name=category.name,
        excluded_branch_ids=[exc.branch_id for exc in exclusions],
    )


@router.put("/exclusions/categories/{category_id}", response_model=CategoryExclusionSummary)
def update_category_exclusions(
    category_id: int,
    body: ExclusionBulkUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> CategoryExclusionSummary:
    """Update exclusions for a category. Replaces all existing exclusions."""
    tenant_id = user["tenant_id"]

    category = db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.tenant_id == tenant_id,
            Category.is_active == True,
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    if body.excluded_branch_ids:
        branches = db.execute(
            select(Branch).where(
                Branch.id.in_(body.excluded_branch_ids),
                Branch.tenant_id == tenant_id,
            )
        ).scalars().all()
        valid_branch_ids = {b.id for b in branches}
        invalid_ids = set(body.excluded_branch_ids) - valid_branch_ids
        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid branch IDs: {list(invalid_ids)}",
            )

    existing = db.execute(
        select(BranchCategoryExclusion).where(
            BranchCategoryExclusion.category_id == category_id,
            BranchCategoryExclusion.tenant_id == tenant_id,
            BranchCategoryExclusion.is_active == True,
        )
    ).scalars().all()

    for exc in existing:
        soft_delete(db, exc, get_user_id(user), get_user_email(user))

    for branch_id in body.excluded_branch_ids:
        exclusion = BranchCategoryExclusion(
            tenant_id=tenant_id,
            branch_id=branch_id,
            category_id=category_id,
        )
        set_created_by(exclusion, get_user_id(user), get_user_email(user))
        db.add(exclusion)

    db.commit()

    return CategoryExclusionSummary(
        category_id=category.id,
        category_name=category.name,
        excluded_branch_ids=body.excluded_branch_ids,
    )


@router.get("/exclusions/subcategories/{subcategory_id}", response_model=SubcategoryExclusionSummary)
def get_subcategory_exclusions(
    subcategory_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> SubcategoryExclusionSummary:
    """Get exclusion details for a specific subcategory."""
    subcategory = db.scalar(
        select(Subcategory).options(
            joinedload(Subcategory.category)
        ).where(
            Subcategory.id == subcategory_id,
            Subcategory.tenant_id == user["tenant_id"],
            Subcategory.is_active == True,
        )
    )
    if not subcategory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcategory not found",
        )

    exclusions = db.execute(
        select(BranchSubcategoryExclusion).where(
            BranchSubcategoryExclusion.subcategory_id == subcategory_id,
            BranchSubcategoryExclusion.tenant_id == user["tenant_id"],
            BranchSubcategoryExclusion.is_active == True,
        )
    ).scalars().all()

    return SubcategoryExclusionSummary(
        subcategory_id=subcategory.id,
        subcategory_name=subcategory.name,
        category_id=subcategory.category_id,
        category_name=subcategory.category.name if subcategory.category else "Unknown",
        excluded_branch_ids=[exc.branch_id for exc in exclusions],
    )


@router.put("/exclusions/subcategories/{subcategory_id}", response_model=SubcategoryExclusionSummary)
def update_subcategory_exclusions(
    subcategory_id: int,
    body: ExclusionBulkUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> SubcategoryExclusionSummary:
    """Update exclusions for a subcategory. Replaces all existing exclusions."""
    tenant_id = user["tenant_id"]

    subcategory = db.scalar(
        select(Subcategory).options(
            joinedload(Subcategory.category)
        ).where(
            Subcategory.id == subcategory_id,
            Subcategory.tenant_id == tenant_id,
            Subcategory.is_active == True,
        )
    )
    if not subcategory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcategory not found",
        )

    if body.excluded_branch_ids:
        branches = db.execute(
            select(Branch).where(
                Branch.id.in_(body.excluded_branch_ids),
                Branch.tenant_id == tenant_id,
            )
        ).scalars().all()
        valid_branch_ids = {b.id for b in branches}
        invalid_ids = set(body.excluded_branch_ids) - valid_branch_ids
        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid branch IDs: {list(invalid_ids)}",
            )

    existing = db.execute(
        select(BranchSubcategoryExclusion).where(
            BranchSubcategoryExclusion.subcategory_id == subcategory_id,
            BranchSubcategoryExclusion.tenant_id == tenant_id,
            BranchSubcategoryExclusion.is_active == True,
        )
    ).scalars().all()

    for exc in existing:
        soft_delete(db, exc, get_user_id(user), get_user_email(user))

    for branch_id in body.excluded_branch_ids:
        exclusion = BranchSubcategoryExclusion(
            tenant_id=tenant_id,
            branch_id=branch_id,
            subcategory_id=subcategory_id,
        )
        set_created_by(exclusion, get_user_id(user), get_user_email(user))
        db.add(exclusion)

    db.commit()

    return SubcategoryExclusionSummary(
        subcategory_id=subcategory.id,
        subcategory_name=subcategory.name,
        category_id=subcategory.category_id,
        category_name=subcategory.category.name if subcategory.category else "Unknown",
        excluded_branch_ids=body.excluded_branch_ids,
    )
