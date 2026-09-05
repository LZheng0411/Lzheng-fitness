#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a portable, data-free workbench template from a finished HTML page."""

import argparse
import json
import re
from pathlib import Path


DATA_RE = re.compile(
    r'<script id="workbench-data" type="application/json">[\s\S]*?</script>'
)
CLOUDBASE_SDK_RE = re.compile(
    r'\s*<script\s+src=["\']https://static\.cloudbase\.net/[^"\']+["\']\s*></script>\s*',
    re.I,
)
CLOUD_STATE_RE = re.compile(
    r"  var nutritionCloud = \{[\s\S]*?\n  \};\n  var nutritionStorage = \{[\s\S]*?\n  \};"
)
OBSIDIAN_HREF_RE = re.compile(
    r"  function obsidianLocalHref\(relative\)\{[\s\S]*?\n  \}"
)
NUTRITION_CONTRACT_RE = re.compile(
    r"  function nutritionDefaults\(\)\{[\s\S]*?\n  loadNutritionContract\(\);"
)


GENERIC_CLOUD_STATE = """  var integrationConfig=(D.integrations&&D.integrations.cloudbase)||{enabled:false,env_id:'',publishable_key:'',sdk:null,region:'',bucket_name:''};
  var nutritionCloud = {
    enabled:integrationConfig.enabled===true,
    env:String(integrationConfig.env_id||''),
    region:String(integrationConfig.region||''),
    bucketName:String(integrationConfig.bucket_name||''),
    accessKey:String(integrationConfig.publishable_key||''),
    app:null,auth:null,db:null,bucket:null,session:null,userId:null,ready:false,error:null
  };
  var storageInstance=String((D.system&&D.system.instance_id)||'anonymous-shell').replace(/[^a-z0-9-]/gi,'');
  var storagePrefix='fitness.workbench.v1.'+storageInstance+'.'+String(m.source_version||'plan')+'.';
  var nutritionStorage = {
    profile:storagePrefix+'nutrition.profile',
    profilePending:storagePrefix+'nutrition.profile.pending',
    body:storagePrefix+'nutrition.body',
    bodyPending:storagePrefix+'nutrition.body.pending',
    meals:storagePrefix+'nutrition.meals',
    checkins:storagePrefix+'nutrition.checkins',
    checkinsPending:storagePrefix+'nutrition.checkins.pending'
  };"""


GENERIC_SDK_LOADER = r"""  function loadCloudbaseSdk(){
    if(window.cloudbase)return Promise.resolve(true);
    var url=String(integrationConfig.sdk||'');
    if(!/^https:\/\/[A-Za-z0-9.-]+\/[A-Za-z0-9._~:\/?#[\]@!$&'()*+,;=%-]+$/i.test(url))return Promise.resolve(false);
    return new Promise(function(resolve){var tag=document.createElement('script');tag.src=url;tag.async=true;tag.onload=function(){resolve(!!window.cloudbase);};tag.onerror=function(){tag.remove();resolve(false);};document.head.appendChild(tag);});
  }
  async function initNutritionCloud(){
    if(!nutritionCloud.enabled||!nutritionCloud.env||!nutritionCloud.accessKey||!integrationConfig.sdk){enterNutritionLocalMode(null,'未配置可选同步 · 当前使用本机模式');return false;}
    if(!await loadCloudbaseSdk()){enterNutritionLocalMode(null,'云端组件未加载 · 尚未同步，请检查配置');return false;}"""


GENERIC_NUTRITION_CONTRACT = r"""  function nutritionDefaults(){
    return {
      schema_version:2,
      profile:{sex:null,age:null,height_cm:null,current_weight_kg:latestConfirmedWeight()},
      meta:{contract_version:2,status:'awaiting_profile',goal:'maintenance'},
      calculation:{method:'mifflin_st_jeor',activity_factor:1.5,energy_adjustment_percent:0,deficit_percent:0,protein_g_per_kg:2,fat_g_per_kg:.8,carbohydrate_g_per_kg:{heavy_training:4,normal_training:3.5,rest:3},minimum_observation_days:14},
      day_type_rules:{heavy_training:{label:'重训练日',match:[]},normal_training:{label:'普通训练日',match:[]},rest:{label:'休息日',match:['休息','恢复']},needs_confirmation:{label:'待确认',match:[]}}
    };
  }
  function mergeNutritionContract(raw){
    var base=nutritionDefaults();
    if(!raw||typeof raw!=='object')return base;
    base.schema_version=Number(raw.schema_version||base.schema_version);
    base.meta=Object.assign(base.meta,raw.meta||{});
    base.profile=Object.assign(base.profile,raw.profile||{});
    base.calculation=Object.assign(base.calculation,raw.calculation||{});
    base.day_type_rules=Object.assign(base.day_type_rules,raw.day_type_rules||{});
    return base;
  }
  function loadNutritionContract(){
    nutritionContract=mergeNutritionContract(D.nutrition_contract);
    if(document.body.classList.contains('nutrition-open'))renderNutrition();
    return Promise.resolve(nutritionContract);
  }
  loadNutritionContract();"""


def fail(message):
    raise SystemExit("FITNESS_WORKBENCH_TEMPLATE: FAIL\n- " + message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.out).resolve()
    if not source.is_file():
        fail("源 HTML 不存在: " + str(source))

    html = source.read_text(encoding="utf-8")
    if output.exists() and 'id="fitness-local-store"' in output.read_text(encoding="utf-8") and 'id="fitness-local-store"' not in html:
        fail("源页面缺少当前离线记录层，拒绝覆盖已有模板；请先显式迁移离线功能")
    if len(DATA_RE.findall(html)) != 1:
        fail("源 HTML 必须且只能包含一个 workbench-data 数据块")

    html = DATA_RE.sub(
        '<script id="workbench-data" type="application/json">{}</script>',
        html,
        count=1,
    )
    replacements = {
        'content:"LZ / ";': 'content:"__FWB_BRAND__ / ";',
        'content:"LZ\\A TRAINING";': 'content:"__FWB_BRAND__\\A TRAINING";',
        'content:"LZ / TRAINING";': 'content:"__FWB_BRAND__ / TRAINING";',
    }
    for original, portable in replacements.items():
        html = html.replace(original, portable)
    # The personal runtime may use a newer local WebP. The public bundle ships
    # one stable PNG fallback and MP4, so generated projects must reference
    # those portable assets.
    html = html.replace("workbench-background.webp", "workbench-background.png")

    # A finished personal page can contain its live optional-sync adapter.
    # The public template must instead read an anonymous, disabled config from
    # workbench-data and load the SDK only after that config is enabled.
    html = CLOUDBASE_SDK_RE.sub("\n", html)
    html, cloud_count = CLOUD_STATE_RE.subn(GENERIC_CLOUD_STATE, html, count=1)
    if cloud_count != 1:
        fail("没有找到唯一的 CloudBase 运行配置块")
    init_marker = "  async function initNutritionCloud(){\n    setNutritionCloudState('checking','正在检查云端同步');"
    if init_marker not in html:
        fail("没有找到 CloudBase 初始化入口")
    html = html.replace(init_marker, GENERIC_SDK_LOADER, 1)
    html, obsidian_count = OBSIDIAN_HREF_RE.subn(
        "  function obsidianLocalHref(relative){ return ''; }", html, count=1
    )
    if obsidian_count != 1:
        fail("没有找到可选 Obsidian 编辑入口")
    html, nutrition_count = NUTRITION_CONTRACT_RE.subn(
        GENERIC_NUTRITION_CONTRACT, html, count=1
    )
    if nutrition_count != 1:
        fail("没有找到唯一的营养默认值与契约加载块")

    if "__FWB_BRAND__" not in html:
        fail("没有生成品牌占位符，请检查源页面品牌写法")
    absolute_path = r'(?m)(?:^|["\'`\s])([A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)+)'
    if re.search(absolute_path, html):
        fail("模板仍包含 Windows 绝对路径")
    if re.search(r"obsidian://open\?path=[A-Za-z](?:%3A|:)", html, re.I):
        fail("模板仍包含指向固定磁盘的个人 Obsidian 深链")
    forbidden = {
        "live CloudBase environment": r"lzheng-fitness-[a-z0-9]{18,}",
        "live CloudBase domain": r"tcloudbaseapp\.com|tcb-api\.tencentcloudapi\.com",
        "embedded publishable token": r"eyJhbGciOiJSUzI1NiIsImtpZCI6",
        "unconditional CloudBase SDK": r"<script\s+src=[\"']https://static\.cloudbase\.net/",
        "active Obsidian URI": r"obsidian://",
        "personal nutrition defaults": r"profile:\{sex:'male',age:\d+,height_cm:\d+",
        "personal nutrition contract path": r"饮食工作台/营养方案-v\d+\.json",
    }
    for label, pattern in forbidden.items():
        if re.search(pattern, html, re.I):
            fail("模板仍包含 " + label)

    blocks = re.findall(
        r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>',
        html,
    )
    try:
        if json.loads(blocks[0]) != {}:
            fail("模板数据块未清空")
    except json.JSONDecodeError as exc:
        fail("模板数据块不是合法 JSON: " + str(exc))

    from workbench_ui import seal, shell_problems
    issues = shell_problems(html)
    if issues:
        fail("源页面不具备当前独立导航契约：" + ";".join(issues))
    html = seal(html)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html.rstrip() + "\n", encoding="utf-8")
    print("FITNESS_WORKBENCH_TEMPLATE: PASS")
    print("template: " + str(output))


if __name__ == "__main__":
    main()
