# Mobile Release Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans after the operating model below is approved. Implement task-by-task with regression tests; preserve existing builders and store tools.

**Goal:** تحويل «ارفع» إلى عملية نشر متكاملة قابلة للتحقق والاستكمال، يتولى الوكيل قراراتها الفنية المعتادة، ويطلب تدخل المستخدم عند قرار تكلفة أو صلاحية أو تغيير جوهري فقط.

**Architecture:** البناء على mobile-publish الحالي: سياسة ثابتة لكل مشروع، فحص جاهزية موحّد، ملفات بناء مثبتة بالبصمة، وتحقق من المتاجر. نضيف منسقًا خفيفًا وسجل تشغيل لكل إصدار، دون منصة جديدة أو قاعدة بيانات أو إعادة كتابة Fastlane/asc/Shorebird.

**Tech Stack:** المهارة الحالية وPython القياسي وBash وGitHub Actions وأدوات النشر المعتمدة في كل مشروع.

**Spec:** أمثلة المستخدم وموافقاته في هذه المحادثة: استقلال المطوّر عن حساب المالك، دومينو بدون Shorebird، الحفاظ على المشاريع الحالية، Shorebird للجمهور الصغير، التوقف عند تنبيه 400، ونشر من كلمة واحدة مع معالجة الأعطال المعتادة. هذه خطة للمرحلة التالية وليست إذنًا بنشر تطبيق أو تغيير اشتراك أو حذف تطبيق سحابي.

## Outcome and current evidence

المطلوب أن يحدد الوكيل التطبيق والإصدار ونوع الطلب، يفحص الوصول والتكلفة والتوافق، يبني ويفحص مرة واحدة، يرفع ويتحقق من القبول، ويستكمل الجزء الناقص عند الفشل دون تخمين أو إعادة أعمال نجحت.

الموجود بالفعل حتى commit `fb2d017`:

- استدعاء السكيل تلقائيًا في تعليمات Codex وClaude على هذا الجهاز، ومثبت فريق آمن مثبت على commit معتمد.
- سياسة runtime ومتاجر لكل مشروع، وحماية من تبديل Shorebird إلى Flutter أو إضافة متجر بسبب وجود credentials.
- فحص Shorebird للتطبيق والدور باستخدام endpoints قراءة محددة، دون إنشاء حساب/مؤسسة تجريبيًا.
- تحذير يتوقف عند تجاوز 400 جهاز نشط افتراضيًا، أو مشكلة كوتا فعلية؛ البيانات الناقصة لا تُعتبر صفرًا. الإقرار يخص العملية الحالية فقط.
- فصل التحضير عن النقل مع بصمات للملفات والسياسة، وانتظار معالجة Apple.
- 55 اختبارًا ناجحًا على Linux وmacOS في GitHub، run `43048972428`. هذه اختبارات السكيل؛ لا تثبت توقيع أو نجاح إصدار فعلي لأي تطبيق.

الفجوات التي ما زالت تعتمد على تعليمات الوكيل أو إعدادات كل مشروع: توحيد SDK/flavor والبيئة، جمع آخر إصدارات المتاجر، منع تداخل طلبين، سجل تشغيل قابل للاستكمال، توحيد التحقق من كل متجر، والتوزيع الداخلي للمشاريع الكبيرة. حساب عبد الله وجهازه لم يُعدّلا أو يُختبرا فعليًا؛ الاختبارات تحاكي مطوّرًا مستقلًا بلا حساب المالك.

## Global Constraints

- دومينو يظل بدون Shorebird، بما في ذلك عدم إدخاله ضمنيًا لتسريع التجربة.
- لا تغيير runtime أو خطة أو حد إنفاق أو عضوية أو مفاتيح تلقائيًا. تثبيت السكيل لا ينقل أي حساب.
- قواعد المشروع تحدد طريقة البناء؛ توفر أدوات أو credentials على جهاز لا يغيرها.
- «ارفع» داخل مشروع موبايل يعني رفع الإصدار للوجهة المعتمدة، وليس إرسالًا للمراجعة أو ترحيلًا أو حذفًا تلقائيًا.
- OTA يعالج الإصدارات الموجودة بدقة: dry-run ومقارنات native/assets وchecks للمنصتين قبل نشر أي منصة، دون تجاوز التحذيرات.
- استخدام المتاجر/المكتبات الحالية، وحماية changelogs والـmetadata والإعدادات والتعديلات المحلية غير المتعلقة.
- لا تكلفة مُدّعاة لكل مستخدم: Shorebird يحاسب على تثبيت patch بنجاح؛ الأجهزة النشطة مؤشر خطر تقريبي.
- السجلات لا تحتوي أسرارًا أو headers أو روابط موقعة أو محتويات ملفات المفاتيح.
- لا نشر حقيقي لاختبار السكيل، ولا حذف بيانات تطبيق من جهاز شخصي لإثبات launch test.

## Operating model

### Three delivery contexts

| الغرض | المسار |
|---|---|
| تجربة المطوّر على جهازه | Flutter debug/hot reload متى كان مناسبًا، دون رفع متجر أو استهلاك OTA بلا داعٍ. |
| تجربة الفريق/العميل | مسار توزيع داخلي قائم ومُعتمد: APK/Play Internal/TestFlight للمشروع العادي، أو Shorebird للمشروع المصرّح له بعد فحوصه. لا إنشاء flavors أو تطبيقات أو خدمات جديدة تلقائيًا. |
| إصدار للمستخدمين | runtime ومتاجر وبيئة المشروع، وفحوص إصدار وتوقيع ومعالجة وموافقات المراجعة حسب الطلب. |

### Decisions the agent owns

- اكتشاف المشروع الصحيح من السياق والسياسة والـGit remote، واستخدام البيانات المتاحة بدل إعادة سؤال المستخدم عنها.
- قراءة إعداد SDK/flavor/entrypoint/defines من مصدره الموجود، وتشخيص التعارض بدل اختيار أحدث SDK عالمي.
- تنفيذ format/analysis/tests والفحوص المطلوبة، وإصلاح عطل فني داخل النطاق وإعادة فحوصه.
- متابعة CI والأدوات والمتاجر، واختيار المسار المحلي المعتمد عند تعطل CI، دون تعديل فوترة.
- إعادة محاولة عطل نقل مؤقت مرة واحدة بعد التأكد من عدم قبول المتجر للإصدار بالفعل.

### Decisions reserved for the user

- تطبيق/بيئة/متجر غير محسومين فعليًا بعد قراءة السياق، أو نطاق تغييرات سيُنشر غير واضح.
- تجاوز تنبيه الجمهور/الكوتا لهذه العملية، أو تغيير حد التنبيه.
- تركيب/إزالة Shorebird، أو حذف سجلاته السحابية، أو تغيير اشتراك/إنفاق.
- صلاحية أو اعتماد لا يمكن استكماله بالوصول الحالي؛ يُعرض المطلوب بدقة مرة واحدة.

### Shared quota and growth

شرط 400 مؤشر مبكر، وليس ضمانًا لعدم استهلاك الكوتا: تطبيق صغير مع تحديثات متكررة أو عدة تطبيقات صغيرة يشتركون في خطة واحدة قد يستهلكون الحد. نعرض الاستخدام الفعلي للحساب وفترته والمشاريع المساهمة فيه إن سمحت الصلاحيات، ونضيف قرارًا عند اقتراب الحد وفق إشارة الخادم الموثوقة. لا نعتبر غياب البيانات أمانًا، ولا نجمع مستخدمين يوميين أو نفترض تنزيلات المتجر مساوية للمستخدمين النشطين. المرجع: [احتساب تثبيتات patches والكوتا المشتركة](https://docs.shorebird.dev/account/billing/).

عند طلب الخروج من Shorebird: نجهز إصدار متجر عادي على Android وiOS، مع الحفاظ على التوقيع والمعرفات والبيانات، ونفحصه ونوزعه. النسخ القديمة تبقى على runtime القديم حتى التحديث؛ نقل النسخة الجديدة لا يثبت توقف كل استهلاك قديم فورًا. حذف التطبيق السحابي وسجلاته قرار منفصل وصريح بعد تحديد الأثر، وليس نتيجة تلقائية لعبور 400.

## Review Focus

1. مطوّران أو عمليتان لنفس التطبيق يحاولان استخدام رقم إصدار واحد أو رفع ملفات مختلفة.
2. اختلاف SDK/flavor/بيئة أو تغييرات محلية عن الملف الذي تم فحصه، مع بقاء hash صحيح لملف آخر.
3. كوتا مشتركة مرتفعة رغم صغر التطبيق الحالي، أو بيانات قديمة/جزئية؛ لا أمان مزيف ولا تكلفة مخترعة.
4. قبول منصة وفشل أخرى، أو نجاح النقل وفشل المعالجة؛ الاستكمال لا يكرر ما قُبل ولا يدّعي نجاح الكل.
5. CI/صلاحيات/شبكة غير متاحة أو logs تحتوي معلومات حساسة؛ المحافظة على العمل وعرض عائق دقيق.

## Task 1: One authoritative release request and project build context

**Files:** Extend `scripts/publish_policy.py`, `scripts/publish.sh`, `SKILL.md`, `references/project-policy.md`; create `scripts/release_request.py` and its tests only for the normalized operation/context shared by the coordinator and verification.

**Interfaces:** A resolved request identifies application root, operation (`store_upload`, `ota_patch`, `store_review`, `runtime_migration`), approved destinations, source snapshot, and references to the project's existing SDK/flavor/target/environment configuration. It never contains credential values. Runtime policy remains authoritative; account capability is a separate result.

- [ ] إثبات الحالات الفاشلة: monorepo متعدد التطبيقات، SDK مختلف، flavor/entrypoint غير مطابق، متجر غير معتمد، وسياق رفع عادي يُفهم خطأ كـpatch أو مراجعة.
- [ ] توحيد resolution وإبقاء كل قاعدة في مكان واحد؛ لا نسخ منطق runtime/quota/auth داخل المنسق.
- [ ] تثبيت مصدر إعداد SDK القائم بدل نسخ قيمته بين ملفات متعددة أو استخدام `system` بلا تحقق. إعداد جديد يظهر فقط عند غياب مصدر واضح.
- [ ] تكييف المسارات القائمة تدريجيًا بدل تجاوز Fastlane أو نسخ قواعده. نقص الوصول لا يغير طريقة البناء.
- [ ] تشغيل مجموعة الاختبارات ومراجعة diff ثم commit محدد لهذه المهمة.

## Task 2: A resumable run with immutable evidence

**Files:** Create `scripts/release_run.py` and `scripts/test_release_run.py`; extend `scripts/prepared_release.py` and the publisher entrypoint as needed.

**Interfaces:** A run records a unique ID, app/source/operation, actual build inputs, artifact SHA256, each target's state and store/Shorebird references. Evidence survives `flutter clean`; no secrets or full environment dump. The coordinator invokes existing builders and gates; it does not become a generic workflow framework.

- [ ] كتابة اختبارات فشل لانقطاع بعد البناء، تعارض ملف/سياسة، تكرار الطلب، وطلبين محليين متزامنين.
- [ ] إضافة local lock محدد بالتطبيق ومنع duplicate submissions. في CI يكون قفل النشر بالتطبيق/البيئة، لا بالفرع فقط.
- [ ] عدم الادعاء بأن قفل الجهاز يمنع مطوّرًا آخر: الرفع المركزي المعتمد عبر CI هو آلية التنسيق المفضلة للفريق. الفحص المحلي لا يقدم ضمان distributed lock.
- [ ] حفظ سجل مختصر قابل للاستكمال والملفات المفحوصة نفسها؛ لا إعادة بناء لحل عطل نقل، ولا الاحتفاظ بنسخ بلا حد أو حذف artifacts ما زالت لازمة لعملية مفتوحة.
- [ ] توفير ملخص حالة واحد: جاهزية، بناء، فحص ملف، نقل، معالجة/قبول، ومراجعة إن طُلبت. لا اختزالها في succeeded=true.
- [ ] اختبار الاستكمال بعد restart وانقطاع شبكة دون تعريض بيانات المصدر أو الأسرار، ثم تشغيل المجموعة وcommit.

## Task 3: Store verification, version selection and bounded recovery

**Files:** Extend the existing publisher and store references. Create `scripts/store_status.py` and tests if needed for a shared normalized result; reuse asc/Fastlane/AGC tooling rather than reproducing their upload APIs.

**Interfaces:** Store status is scoped to the exact app, version/build, platform and track. It distinguishes uploaded, processing, accepted and rejected. A failed transport is queried before retry. Version selection reads available live evidence and the project's version source; it does not assume an incomplete track list proves a number was never used.

- [ ] اختبار duplicate build number، تطبيق/track خاطئ، صلاحية قراءة بلا نشر، signing خاطئ، processing reject، ونجاح منصة واحدة فقط.
- [ ] حل تداخل الترقيم مع قفل العملية؛ رفض التخمين عند نقص evidence بدل build طويل ثم retry عشوائي برقم أعلى.
- [ ] فحص توقيع ومحتوى الملف النهائي ومعرفاته ونسخته؛ launch test على بيئة QA/محاكي مخصص مع إثبات النسخة المثبتة، دون uninstall لتطبيق المستخدم الشخصي.
- [ ] التحقق من قبول المتجر من API بعد النقل. retry واحد للأخطاء المؤقتة فقط وبعد الاستعلام عن النسخة؛ لا تكرار إصدار قُبل أو إرسال مراجعة غير مطلوبة.
- [ ] التعامل الصريح مع partial publication. OTA يحتفظ ببوابة المنصتين قبل أول رفع، مع تقرير دقيق لو فشل نقل الثانية بعد قبول الأولى؛ لا rollback تلقائي.
- [ ] تصنيف فشل CI/runner والـlogs والشبكة، وتنقية رسائل الخطأ بما فيها الروابط الموقعة. النقل أو صلاحية الحساب لا يُعالجان بتغيير runtime أو الإنفاق.
- [ ] تشغيل المجموعة ومراجعة evidence ثم commit.

## Task 4: Team adoption, fast internal distribution and retirement procedure

**Files:** Extend `references/team-publishing.md`, `references/shorebird-usage.md`, store runbooks and CI verification. Application-specific workflow changes are reviewed commits in their own repositories; no application deployment as a side effect of skill testing.

- [ ] تجربة النموذج على دومينو كمشروع Flutter/Fastlane، و3M كمشروع Shorebird. البداية بفحص وتوليد أدلة دون نشر فعلي؛ أي signed/store release لاحق يحتاج طلب الإصدار المقصود.
- [ ] تحديد مسار تجربة سريع للمشروع من الموجود: hot reload للمطور، وتوزيع داخلي للفريق. دومينو يستفيد من التوزيع الآلي بدون إدخال Shorebird.
- [ ] تجهيز onboard check لكل مطوّر بأدواته وصلاحياته؛ فحص آلي نظيف لحالة زميل بلا حساب المالك. لا الادعاء بإعداد جهاز عبد الله قبل اختباره عنده.
- [ ] إضافة تقييم الكوتا المشتركة إلى release decision، وتوثيق مسار الانتقال إلى متجر عادي وانتشار الإصدار القديم/الجديد دون حذف سحابي تلقائي.
- [ ] تثبيت نسخ السكيل المعتمدة للفريق مع المحافظة على التعديلات المحلية، واختبار عدم تحول تحديث السكيل إلى تعديل مشروع/حساب غير مطلوب.
- [ ] تشغيل كل اختبارات السكيل على Linux وmacOS لنفس commit. اختبارات PR بلا أسرار؛ jobs النشر الحقيقية منفصلة عن اختبارات المهارة ولا تبدأ من PR غير موثوق.
- [ ] قياس وقت كل مرحلة ونسبة الإعادات قبل ادعاء تسريع. caching للاعتمادات المسموح بها مع تثبيت المدخلات؛ الملف النهائي المفحوص يبقى هو الملف المرفوع.
- [ ] مراجعة مستقلة، ثم rollout تدريجي وعرض النتيجة النهائية والحدود المتبقية.

## Completion criteria

- «ارفع» ينتج مسارًا واحدًا معلومًا لكل مشروع وملخصًا دقيقًا بالنسخة والوجهات والقبول، دون أسئلة تقنية يمكن حلها من الموجود.
- لا مشروع عادي يكتسب اعتماد Shorebird، ولا زميل يحتاج حساب المالك، ولا يصبح حد 400 أمانًا مزيفًا للكوتا المشتركة.
- الانقطاع والتكرار والتزامن لا يؤديان تلقائيًا لإعادة بناء أو رفع أو ترقيم غير مدروس.
- معالجة الفشل تستكمل الهدف الموافق عليه وتحافظ على العمل، مع تدخل المستخدم عند قرار فعلي فقط.
- التوقيع والمتاجر وCI والتكلفة لا تختلط في عبارة نجاح واحدة؛ الأدلة مرتبطة بنفس الملف والمصدر.
- التنفيذ المرحلي يضيف مسؤوليات لها مستهلكون حقيقيون، ويحافظ على بساطة السكيل وقابلية استخدامها عبر المشاريع.

## Suggested execution order

1. توحيد اكتشاف الطلب وسياق المشروع، ثم سجل التشغيل والاستكمال؛ هذا يعالج اللخبطة والتكرار أولًا.
2. توحيد أدلة قبول المتاجر والترقيم والتعافي من الفشل، ثم تطبيق مساري دومينو و3M.
3. تحسين التوزيع الداخلي وتجهيز الفريق ومراقبة الميزانية في نفس المسار؛ لا بناء منصة جديدة أو إضافة كل حالات العالم مقدمًا.

الخطة تُراجع كنموذج تشغيل كامل. ما تم اعتماده وتنفيذه بالفعل يبقى كما هو؛ هذه المرحلة لا تُنفذ بمجرد حفظ الوثيقة.
