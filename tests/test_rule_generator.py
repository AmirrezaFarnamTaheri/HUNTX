# Tests for Smart Domain-Categorized DNS & Outbound Rule Generator
# Authority: Sing-box Route Rule Specification & Clash Rule-Set Spec
from huntx.pipeline.rule_gen import SmartRuleGenerator, RuleCategory

def test_rule_category_enum():
    assert RuleCategory.STREAMING.value == "streaming"
    assert RuleCategory.AI.value == "ai"
    assert RuleCategory.DEVELOPER.value == "developer"
    assert RuleCategory.DOMESTIC_DIRECT.value == "domestic_direct"
    assert RuleCategory.AD_BLOCKING.value == "ad_blocking"

def test_rule_generator_generates_categorized_rulesets():
    gen = SmartRuleGenerator()
    singbox_rules = gen.generate_singbox_rules()
    
    # Verify categories exist in Sing-box rules
    outbounds = [r.get("outbound") for r in singbox_rules]
    assert "PROXY-STREAMING" in outbounds
    assert "PROXY-AI" in outbounds
    assert "direct" in outbounds
    assert "block" in outbounds

    clash_rules = gen.generate_clash_rules()
    assert any("DOMAIN-SUFFIX,netflix.com,PROXY-STREAMING" in r for r in clash_rules)
    assert any("DOMAIN-SUFFIX,openai.com,PROXY-AI" in r for r in clash_rules)
    assert any("DOMAIN-SUFFIX,github.com,PROXY-DEV" in r for r in clash_rules)
    assert any("GEOIP,CN,DIRECT" in r for r in clash_rules)
