import pytest
from playwright.sync_api import Page, expect


@pytest.mark.server
def test_reject_improper_login_attempts(page: Page) -> None:
    page.goto("http://localhost:8501/")

    page.get_by_test_id("stBaseButton-secondaryFormSubmit").click()
    expect(page.get_by_test_id("stAlert").get_by_role("paragraph")).to_contain_text(
        "Login failed"
    )

    page.get_by_label("username").click()
    page.get_by_label("username").fill("user")
    page.get_by_test_id("stBaseButton-secondaryFormSubmit").click()
    expect(page.get_by_test_id("stAlert").get_by_role("paragraph")).to_contain_text(
        "Login failed"
    )

    page.get_by_label("password", exact=True).click()
    page.get_by_label("password", exact=True).fill("dummy")
    page.get_by_test_id("stBaseButton-secondaryFormSubmit").click()
    expect(page.get_by_test_id("stAlert").get_by_role("paragraph")).to_contain_text(
        "Login failed"
    )

    page.get_by_label("username").click()
    page.get_by_label("username").fill("")
    page.get_by_test_id("stBaseButton-secondaryFormSubmit").click()
    expect(page.get_by_test_id("stAlert").get_by_role("paragraph")).to_contain_text(
        "Login failed"
    )
