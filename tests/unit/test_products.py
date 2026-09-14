import pytest

from tophost_api.client.products import ProductParser
from tophost_api.errors import (
    AmbiguousDomainError,
    DomainNotFoundError,
)


def test_discovers_single_product():
    html = """
    <html>
      <body>
        <div class="product">
          <h3>example.com</h3>
          <a href="index_th.php?option=com_thutente&Itemid=143&func=dd1234567">
            Control panel
          </a>
        </div>
      </body>
    </html>
    """

    products = ProductParser().parse(html)

    assert len(products) == 1
    assert products[0].domain == "example.com"
    assert products[0].product_id == "1234567"
    assert (
        products[0].control_panel_href
        == "https://www.tophost.it/myth/"
        "index_th.php?option=com_thutente&Itemid=143&func=dd1234567"
    )


def test_discovers_multiple_products():
    html = """
    <div id="account">
      <section>
        <strong>alpha.it</strong>
        <a href="index_th.php?func=dd111">CP</a>
      </section>

      <section>
        <strong>beta.example</strong>
        <a href="index_th.php?func=dd222">CP</a>
      </section>
    </div>
    """

    products = ProductParser().parse(html)

    assert [
        (product.domain, product.product_id)
        for product in products
    ] == [
        ("alpha.it", "111"),
        ("beta.example", "222"),
    ]


def test_resolves_domain_case_insensitively():
    html = """
    <article>
      <span>Example.COM</span>
      <a href="index_th.php?func=dd7654321">CP</a>
    </article>
    """

    product = ProductParser().resolve(
        html,
        " EXAMPLE.com. ",
    )

    assert product.domain == "example.com"
    assert product.product_id == "7654321"


def test_optional_product_id_override():
    html = """
    <main>
      <section>
        <span>example.com</span>
        <a href="index_th.php?func=dd111">CP</a>
      </section>

      <section>
        <span>example.com</span>
        <a href="index_th.php?func=dd222">CP</a>
      </section>
    </main>
    """

    product = ProductParser().resolve(
        html,
        "example.com",
        product_id_override="222",
    )

    assert product.product_id == "222"


def test_ambiguous_domain_without_override_is_rejected():
    html = """
    <main>
      <section>
        <span>example.com</span>
        <a href="index_th.php?func=dd111">CP</a>
      </section>

      <section>
        <span>example.com</span>
        <a href="index_th.php?func=dd222">CP</a>
      </section>
    </main>
    """

    with pytest.raises(AmbiguousDomainError):
        ProductParser().resolve(
            html,
            "example.com",
        )


def test_unknown_domain_is_rejected():
    html = """
    <section>
      <span>example.com</span>
      <a href="index_th.php?func=dd111">CP</a>
    </section>
    """

    with pytest.raises(DomainNotFoundError):
        ProductParser().resolve(
            html,
            "missing.example",
        )


def test_tophost_domains_are_not_product_domains():
    html = """
    <section>
      <span>example.com</span>
      <span>www.tophost.it</span>
      <a href="index_th.php?func=dd111">CP</a>
    </section>
    """

    product = ProductParser().resolve(
        html,
        "example.com",
    )

    assert product.product_id == "111"


def test_does_not_guess_across_product_boundary():
    html = """
    <main>
      <section>
        <span>alpha.it</span>
        <span>beta.it</span>
        <a href="index_th.php?func=dd111">CP</a>
      </section>
    </main>
    """

    products = ProductParser().parse(html)

    assert products == []
