from modules.cs2_updates.cs2_updates import CS2Updates


def test_format_article_html_preserves_sections_and_nested_lists():
    html = """
    <div class="EventDetailsBody A_A2B6fTn_MPLlGCmsLtd">
      <p>[ PREMIER ]<wbr></p>
      <ul>
        <li><p>Premier Season Five has begun<wbr></p></li>
        <li><p>Added Cache to the Active Duty Map Pool<wbr></p></li>
        <li><p>Removed Overpass from the Active Duty Map Pool<wbr></p></li>
      </ul>
      <p><wbr></p>
      <p>[ GAMEPLAY ]<wbr></p>
      <ul>
        <li>
          <p>Re-designed effective range and extent of C4 explosion damage on all official defusal-mode maps.<wbr></p>
          <ul>
            <li><p>Damage is now applied according to precomputed simulation values, baked into the compiled map.<wbr></p></li>
            <li><p>Explosion shockwave damage now rapidly expands from the center of the explosion instead of being applied instantly.<wbr></p></li>
          </ul>
        </li>
      </ul>
    </div>
    """

    cog = CS2Updates(bot=None)
    output = cog._format_article_html(html, title="Counter-Strike 2 Update", limit=2000)

    assert "**[ PREMIER ]**" in output
    assert "• Premier Season Five has begun" in output
    assert "• Added Cache to the Active Duty Map Pool" in output
    assert "**[ GAMEPLAY ]**" in output
    assert "• Re-designed effective range and extent of C4 explosion damage on all official defusal-mode maps." in output
    assert "  • Damage is now applied according to precomputed simulation values, baked into the compiled map." in output
    assert "  • Explosion shockwave damage now rapidly expands from the center of the explosion instead of being applied instantly." in output


def test_format_article_html_preserves_update_notes_links():
    html = """
    <div class="EventDetailsBody A_A2B6fTn_MPLlGCmsLtd">
      <p>[ MAPS ]<wbr></p>
      <p>Boulder<wbr></p>
      <ul>
        <li>
          <p>Updated to the latest version from the Community Workshop (<a href="https://steamcommunity.com/sharedfiles/filedetails/changelog/3663186989">Update Notes</a>).<wbr></p>
        </li>
      </ul>
      <p>Fachwerk<wbr></p>
      <ul>
        <li>
          <p>Updated to the latest version from the Community Workshop (<a href="https://steamcommunity.com/sharedfiles/filedetails/changelog/3442040035">Update Notes</a>).<wbr></p>
        </li>
      </ul>
      <p>Shelter<wbr></p>
      <ul>
        <li>
          <p>Updated to the latest version from the Community Workshop (<a href="https://steamcommunity.com/sharedfiles/filedetails/changelog/3737179295">Update Notes</a>).<wbr></p>
        </li>
      </ul>
    </div>
    """

    cog = CS2Updates(bot=None)
    output = cog._format_article_html(html, title="Counter-Strike 2 Update", limit=2000)

    assert "[Update Notes](https://steamcommunity.com/sharedfiles/filedetails/changelog/3663186989)" in output
    assert "[Update Notes](https://steamcommunity.com/sharedfiles/filedetails/changelog/3442040035)" in output
    assert "[Update Notes](https://steamcommunity.com/sharedfiles/filedetails/changelog/3737179295)" in output


def test_extract_first_image_from_html_prefers_article_content():
    hero_url = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/730/ss_352666c1949ce3966bd966d6ea5a1afd532257bc.jpg?t=1780435263"
    html = f"""
    <div class="_3aht--c1L66YvvpY-Il67f">
      <div class="stsss-bTNuazY8FYtvTOX" style="background-image: url(&quot;{hero_url}&quot;);"></div>
      <div class="EventDetailsBody A_A2B6fTn_MPLlGCmsLtd">
        <p>[ MAPS ]<wbr></p>
        <ul><li><p>Cache<wbr></p></li></ul>
      </div>
    </div>
    """

    cog = CS2Updates(bot=None)
    assert cog._extract_first_image_from_html(html, base_url="https://store.steampowered.com/news/app/730/view/123") == hero_url


def test_format_article_html_falls_back_to_meta_description_sections():
    html = """
    <html>
      <head>
        <meta property="og:description" content="[ MAPS ]&#10;Cache&#10;Fixed various gaps in map.&#10;Fixed a wallbang spot on B site.&#10;[ MAP SCRIPTING ]&#10;Reworked CSPlayerCamera:">
      </head>
      <body><div id="application_root"></div></body>
    </html>
    """

    cog = CS2Updates(bot=None)
    output = cog._format_article_html(html, title="Counter-Strike 2 Update", limit=2000)

    assert "**[ MAPS ]**" in output
    assert "**Cache**" in output
    assert "• Fixed various gaps in map." in output
    assert "• Fixed a wallbang spot on B site." in output
    assert "**[ MAP SCRIPTING ]**" in output
    assert "• Reworked CSPlayer\u200bCamera:" in output


def test_format_article_text_preserves_meta_description_sections():
    text = """[ MAPS ]
Cache
Fixed various gaps in map.
Fixed a wallbang spot on B site.
[ MAP SCRIPTING ]
Reworked CSPlayerCamera:"""

    cog = CS2Updates(bot=None)
    output = cog._format_article_text(text, title="Counter-Strike 2 Update", limit=2000)

    assert output.startswith("**[ MAPS ]**\n\n**Cache**")
    assert "• Fixed various gaps in map." in output
    assert "**[ MAP SCRIPTING ]**" in output
    assert "• Reworked CSPlayer\u200bCamera:" in output
