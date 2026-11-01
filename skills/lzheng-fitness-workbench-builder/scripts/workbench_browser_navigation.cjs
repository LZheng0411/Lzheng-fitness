'use strict';
// Exercise the actual visible navigation, including secondary trend/settings entries.
function rail(page){return page.locator('.px-desktop-rail:visible,.px-mobile-dock:visible,#navBar:visible').first();}
async function navigate(page,key){
  const direct=page.locator('.px-nav-link[data-px-page="'+key+'"]:visible');
  if(await direct.count()){await direct.first().click();return;}
  if(await page.locator('#pxPreviewRoot').count()){
    if(key==='trend'){await navigate(page,'record');await page.getByRole('button',{name:'力量与体重趋势 ↗',exact:true}).click();return;}
    if(key==='settings'){await page.locator('[data-theme-settings]:visible').first().click();return;}
  }
  await page.locator('#navBar a[data-k="'+key+'"]:visible').click();
}
module.exports={navigate,rail};
