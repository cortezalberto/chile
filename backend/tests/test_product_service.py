"""
Tests for ProductService - the core product management service.

Tests cover:
- CRUD operations (create, read, update, delete)
- Branch pricing management
- Allergen management
- Validation rules
- Edge cases and error handling
"""

import pytest
from rest_api.models import (
    Product,
    Category,
    BranchProduct,
    Allergen,
    ProductAllergen,
    Subcategory,
)
from rest_api.services.domain import ProductService
from shared.utils.exceptions import ValidationError, NotFoundError
from tests.conftest import next_id


class TestProductServiceCreate:
    """Tests for ProductService.create_full()"""

    @pytest.fixture
    def product_service(self, db_session):
        """Get a ProductService instance."""
        return ProductService(db_session)

    @pytest.fixture
    def seed_category(self, db_session, seed_branch, seed_tenant):
        """Create a test category."""
        category = Category(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            name="Burgers",
            icon="🍔",
            order=1,
        )
        db_session.add(category)
        db_session.commit()
        db_session.refresh(category)
        return category

    @pytest.fixture
    def seed_allergen(self, db_session, seed_tenant):
        """Create a test allergen."""
        allergen = Allergen(
            id=next_id(),
            tenant_id=seed_tenant.id,
            name="Gluten",
            icon="🌾",
            severity="HIGH",
        )
        db_session.add(allergen)
        db_session.commit()
        db_session.refresh(allergen)
        return allergen

    def test_create_basic_product(
        self, product_service, seed_category, seed_branch, seed_tenant
    ):
        """Can create a basic product with minimal data."""
        data = {
            "name": "Classic Burger",
            "description": "A delicious classic burger",
            "category_id": seed_category.id,
            "branch_prices": [
                {"branch_id": seed_branch.id, "price_cents": 1500, "is_available": True}
            ],
        }

        result = product_service.create_full(
            data=data,
            tenant_id=seed_tenant.id,
            user_id=1,
            user_email="admin@test.com",
        )

        assert result.name == "Classic Burger"
        assert len(result.branch_prices) == 1
        assert result.branch_prices[0].price_cents == 1500


    def test_create_product_with_allergens(
        self, product_service, seed_category, seed_branch, seed_tenant, seed_allergen
    ):
        """Can create product with allergens."""
        data = {
            "name": "Wheat Bread Burger",
            "category_id": seed_category.id,
            "branch_prices": [
                {"branch_id": seed_branch.id, "price_cents": 1600, "is_available": True}
            ],
            "allergens": [
                {"allergen_id": seed_allergen.id, "presence_type": "CONTAINS"}
            ],
        }

        result = product_service.create_full(
            data=data,
            tenant_id=seed_tenant.id,
            user_id=1,
            user_email="admin@test.com",
        )

        assert len(result.allergens) == 1
        assert result.allergens[0].allergen_id == seed_allergen.id

    def test_create_product_without_name_fails(
        self, product_service, seed_category, seed_branch, seed_tenant
    ):
        """Creating product without name raises ValidationError."""
        data = {
            "category_id": seed_category.id,
            "branch_prices": [
                {"branch_id": seed_branch.id, "price_cents": 1500, "is_available": True}
            ],
        }

        with pytest.raises(ValidationError) as exc_info:
            product_service.create_full(
                data=data,
                tenant_id=seed_tenant.id,
                user_id=1,
                user_email="admin@test.com",
            )

        assert "name" in str(exc_info.value).lower()

    def test_create_product_invalid_category_fails(
        self, product_service, seed_branch, seed_tenant
    ):
        """Creating product with invalid category raises ValidationError."""
        data = {
            "name": "Test Product",
            "category_id": 99999,
            "branch_prices": [
                {"branch_id": seed_branch.id, "price_cents": 1500, "is_available": True}
            ],
        }

        with pytest.raises(ValidationError) as exc_info:
            product_service.create_full(
                data=data,
                tenant_id=seed_tenant.id,
                user_id=1,
                user_email="admin@test.com",
            )

        assert "category" in str(exc_info.value).lower()

    def test_create_product_without_branch_prices_fails(
        self, product_service, seed_category, seed_tenant
    ):
        """Creating product without branch prices raises ValidationError."""
        data = {
            "name": "Test Product",
            "category_id": seed_category.id,
            "branch_prices": [],
        }

        with pytest.raises(ValidationError) as exc_info:
            product_service.create_full(
                data=data,
                tenant_id=seed_tenant.id,
                user_id=1,
                user_email="admin@test.com",
            )

        assert "branch" in str(exc_info.value).lower()


class TestProductServiceRead:
    """Tests for ProductService.get_* and list_* methods."""

    @pytest.fixture
    def product_service(self, db_session):
        return ProductService(db_session)

    @pytest.fixture
    def existing_product(self, db_session, seed_category, seed_branch, seed_tenant):
        """Create a product in the database."""
        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
            name="Existing Product",
        )
        db_session.add(product)
        db_session.flush()

        branch_product = BranchProduct(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            product_id=product.id,
            price_cents=2000,
            is_available=True,
        )
        db_session.add(branch_product)
        db_session.commit()
        db_session.refresh(product)
        return product

    @pytest.fixture
    def seed_category(self, db_session, seed_branch, seed_tenant):
        category = Category(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            name="Test Category",
            icon="🍕",
            order=1,
        )
        db_session.add(category)
        db_session.commit()
        db_session.refresh(category)
        return category

    def test_get_product_by_id(
        self, product_service, existing_product, seed_tenant
    ):
        """Can get a product by ID."""
        result = product_service.get_with_relations(
            product_id=existing_product.id,
            tenant_id=seed_tenant.id,
        )

        assert result.id == existing_product.id
        assert result.name == "Existing Product"

    def test_get_product_not_found(self, product_service, seed_tenant):
        """Getting non-existent product raises NotFoundError."""
        with pytest.raises(NotFoundError):
            product_service.get_with_relations(
                product_id=99999,
                tenant_id=seed_tenant.id,
            )

    def test_list_products(
        self, product_service, existing_product, seed_tenant
    ):
        """Can list all products for a tenant."""
        results = product_service.list_with_relations(tenant_id=seed_tenant.id)

        assert len(results) >= 1
        names = [p.name for p in results]
        assert "Existing Product" in names

    def test_list_products_by_category(
        self, product_service, db_session, existing_product, seed_tenant, seed_category, seed_branch
    ):
        """Can filter products by category."""
        # Create another product in a different category
        other_category = Category(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            name="Other Category",
            icon="🍟",
            order=2,
        )
        db_session.add(other_category)
        db_session.flush()

        other_product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=other_category.id,
            name="Other Product",
        )
        db_session.add(other_product)
        db_session.commit()

        # Filter by original category
        results = product_service.list_with_relations(
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
        )

        assert len(results) == 1
        assert results[0].name == "Existing Product"

    def test_list_products_by_branch(
        self, product_service, existing_product, seed_tenant, seed_branch
    ):
        """Can filter products by branch."""
        results = product_service.list_with_relations(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
        )

        assert len(results) >= 1
        # All results should have this branch in their prices
        for product in results:
            branch_ids = [bp.branch_id for bp in product.branch_prices]
            assert seed_branch.id in branch_ids

    def test_list_products_pagination(
        self, product_service, db_session, seed_tenant, seed_category, seed_branch
    ):
        """Can paginate product results."""
        # Create 5 products
        for i in range(5):
            product = Product(
                id=next_id(),
                tenant_id=seed_tenant.id,
                category_id=seed_category.id,
                name=f"Product {i}",
            )
            db_session.add(product)
            db_session.flush()
            bp = BranchProduct(
                id=next_id(),
                tenant_id=seed_tenant.id,
                branch_id=seed_branch.id,
                product_id=product.id,
                price_cents=1000 + i * 100,
                is_available=True,
            )
            db_session.add(bp)
        db_session.commit()

        # Get first 2
        page1 = product_service.list_with_relations(
            tenant_id=seed_tenant.id,
            limit=2,
            offset=0,
        )
        assert len(page1) == 2

        # Get next 2
        page2 = product_service.list_with_relations(
            tenant_id=seed_tenant.id,
            limit=2,
            offset=2,
        )
        assert len(page2) == 2

        # Ensure different products
        page1_ids = {p.id for p in page1}
        page2_ids = {p.id for p in page2}
        assert page1_ids.isdisjoint(page2_ids)


class TestProductServiceUpdate:
    """Tests for ProductService.update_full()"""

    @pytest.fixture
    def product_service(self, db_session):
        return ProductService(db_session)

    @pytest.fixture
    def seed_category(self, db_session, seed_branch, seed_tenant):
        category = Category(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            name="Test Category",
            icon="🍕",
            order=1,
        )
        db_session.add(category)
        db_session.commit()
        db_session.refresh(category)
        return category

    @pytest.fixture
    def existing_product(self, db_session, seed_category, seed_branch, seed_tenant):
        """Create a product in the database."""
        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
            name="Update Test Product",
            description="Original description",
        )
        db_session.add(product)
        db_session.flush()

        branch_product = BranchProduct(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            product_id=product.id,
            price_cents=2000,
            is_available=True,
        )
        db_session.add(branch_product)
        db_session.commit()
        db_session.refresh(product)
        return product

    def test_update_product_name(
        self, product_service, existing_product, seed_tenant
    ):
        """Can update product name."""
        result = product_service.update_full(
            product_id=existing_product.id,
            data={"name": "Updated Name"},
            tenant_id=seed_tenant.id,
            user_id=1,
            user_email="admin@test.com",
        )

        assert result.name == "Updated Name"

    def test_update_product_description(
        self, product_service, existing_product, seed_tenant
    ):
        """Can update product description."""
        result = product_service.update_full(
            product_id=existing_product.id,
            data={"description": "New description"},
            tenant_id=seed_tenant.id,
            user_id=1,
            user_email="admin@test.com",
        )

        assert result.description == "New description"

    def test_update_product_price(
        self, product_service, existing_product, seed_tenant, seed_branch
    ):
        """Can update product branch price."""
        result = product_service.update_full(
            product_id=existing_product.id,
            data={
                "branch_prices": [
                    {"branch_id": seed_branch.id, "price_cents": 2500, "is_available": True}
                ],
            },
            tenant_id=seed_tenant.id,
            user_id=1,
            user_email="admin@test.com",
        )

        assert result.branch_prices[0].price_cents == 2500

    def test_update_nonexistent_product_fails(
        self, product_service, seed_tenant
    ):
        """Updating non-existent product raises NotFoundError."""
        with pytest.raises(NotFoundError):
            product_service.update_full(
                product_id=99999,
                data={"name": "New Name"},
                tenant_id=seed_tenant.id,
                user_id=1,
                user_email="admin@test.com",
            )


class TestProductServiceDelete:
    """Tests for ProductService.delete_product()"""

    @pytest.fixture
    def product_service(self, db_session):
        return ProductService(db_session)

    @pytest.fixture
    def seed_category(self, db_session, seed_branch, seed_tenant):
        category = Category(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            name="Delete Test Category",
            icon="🗑️",
            order=1,
        )
        db_session.add(category)
        db_session.commit()
        db_session.refresh(category)
        return category

    @pytest.fixture
    def deletable_product(self, db_session, seed_category, seed_branch, seed_tenant):
        """Create a product that can be deleted."""
        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
            name="To Be Deleted",
        )
        db_session.add(product)
        db_session.flush()

        bp = BranchProduct(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            product_id=product.id,
            price_cents=1000,
            is_available=True,
        )
        db_session.add(bp)
        db_session.commit()
        db_session.refresh(product)
        return product

    def test_soft_delete_product(
        self, product_service, db_session, deletable_product, seed_tenant
    ):
        """Can soft delete a product."""
        product_service.delete_product(
            product_id=deletable_product.id,
            tenant_id=seed_tenant.id,
            user_id=1,
            user_email="admin@test.com",
        )

        # Refresh and check is_active
        db_session.refresh(deletable_product)
        assert deletable_product.is_active is False

    def test_deleted_product_not_in_list(
        self, product_service, db_session, deletable_product, seed_tenant
    ):
        """Deleted products are excluded from list by default."""
        # Delete the product
        product_service.delete_product(
            product_id=deletable_product.id,
            tenant_id=seed_tenant.id,
            user_id=1,
            user_email="admin@test.com",
        )

        # List products
        results = product_service.list_with_relations(tenant_id=seed_tenant.id)

        # Deleted product should not be in results
        product_ids = [p.id for p in results]
        assert deletable_product.id not in product_ids

    def test_can_include_deleted_in_list(
        self, product_service, db_session, deletable_product, seed_tenant
    ):
        """Can include deleted products in list with flag."""
        # Delete the product
        product_service.delete_product(
            product_id=deletable_product.id,
            tenant_id=seed_tenant.id,
            user_id=1,
            user_email="admin@test.com",
        )

        # List products including inactive
        results = product_service.list_with_relations(
            tenant_id=seed_tenant.id,
            include_inactive=True,
        )

        # Deleted product should be in results
        product_ids = [p.id for p in results]
        assert deletable_product.id in product_ids

    def test_delete_nonexistent_product_fails(
        self, product_service, seed_tenant
    ):
        """Deleting non-existent product raises NotFoundError."""
        with pytest.raises(NotFoundError):
            product_service.delete_product(
                product_id=99999,
                tenant_id=seed_tenant.id,
                user_id=1,
                user_email="admin@test.com",
            )


class TestProductServiceBranchPrices:
    """Tests for branch pricing functionality."""

    @pytest.fixture
    def product_service(self, db_session):
        return ProductService(db_session)

    @pytest.fixture
    def seed_category(self, db_session, seed_branch, seed_tenant):
        category = Category(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            name="Price Test Category",
            icon="💰",
            order=1,
        )
        db_session.add(category)
        db_session.commit()
        db_session.refresh(category)
        return category

    @pytest.fixture
    def second_branch(self, db_session, seed_tenant):
        """Create a second branch for multi-branch tests."""
        from rest_api.models import Branch
        branch = Branch(
            id=next_id(),
            tenant_id=seed_tenant.id,
            name="Second Branch",
            slug="second-branch",
            address="456 Test Ave",
            phone="+1987654321",
            opening_time="10:00",
            closing_time="21:00",
        )
        db_session.add(branch)
        db_session.commit()
        db_session.refresh(branch)
        return branch

    def test_create_product_multiple_branches(
        self, product_service, seed_category, seed_branch, second_branch, seed_tenant
    ):
        """Can create product with prices in multiple branches."""
        data = {
            "name": "Multi-Branch Product",
            "category_id": seed_category.id,
            "branch_prices": [
                {"branch_id": seed_branch.id, "price_cents": 2000, "is_available": True},
                {"branch_id": second_branch.id, "price_cents": 2200, "is_available": True},
            ],
        }

        result = product_service.create_full(
            data=data,
            tenant_id=seed_tenant.id,
            user_id=1,
            user_email="admin@test.com",
        )

        assert len(result.branch_prices) == 2
        prices = {bp.branch_id: bp.price_cents for bp in result.branch_prices}
        assert prices[seed_branch.id] == 2000
        assert prices[second_branch.id] == 2200

    def test_product_available_in_specific_branch(
        self, product_service, db_session, seed_category, seed_branch, second_branch, seed_tenant
    ):
        """Can set product as unavailable in specific branch."""
        data = {
            "name": "Limited Product",
            "category_id": seed_category.id,
            "branch_prices": [
                {"branch_id": seed_branch.id, "price_cents": 1800, "is_available": True},
                {"branch_id": second_branch.id, "price_cents": 1800, "is_available": False},
            ],
        }

        result = product_service.create_full(
            data=data,
            tenant_id=seed_tenant.id,
            user_id=1,
            user_email="admin@test.com",
        )

        availability = {bp.branch_id: bp.is_available for bp in result.branch_prices}
        assert availability[seed_branch.id] is True
        assert availability[second_branch.id] is False
