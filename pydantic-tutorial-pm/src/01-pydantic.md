## 0. 开篇：为什么产品经理要懂 Pydantic

你写 PRD 的时候，一定写过类似这样的东西：

| 字段 | 类型 | 必填 | 规则 | 说明 |
|---|---|---|---|---|
| 手机号 | 文本 | 是 | 11 位，1 开头 | 用于登录和短信通知 |
| 年龄 | 整数 | 否 | 18–120 | 未成年不允许下单 |
| 会员等级 | 枚举 | 是 | 普通 / 白银 / 黄金 | 影响折扣计算 |

这张表就是 PRD 里最常见的「字段规则表」。工程师拿到它之后，要做三件事：

1. 把这张表**翻译成代码里的数据结构**；
2. 在系统边界上**逐条检查**外部传进来的数据是否符合这张表；
3. 把检查通过的数据**再吐出去**给下游（存数据库、返回给前端、发给第三方）。

**Pydantic 干的就是这三件事**。它让工程师只写一次「字段规则表」，检查逻辑、错误提示、对外文档全部自动生成。

一句话定义：

> **Pydantic 是一个「把 PRD 字段规则表变成可执行代码」的 Python 库。**

而对本书后面的内容来说，还有一个更关键的理由：**Pydantic AI 让大模型按固定格式输出结构化结果，靠的就是 Pydantic 的 JSON Schema 生成能力**。你在 Pydantic 里画的那张表，会被自动翻译成一份「给大模型看的填表说明书」。所以第 7 章 JSON Schema 是全书承上启下的一节，请重点看。

本教程所有代码都在 **Pydantic 2.13.4 / Python 3.11** 上真实运行过，输出是真实复制粘贴的（为节省篇幅，部分报错输出省略了末尾的 `For further information visit https://errors.pydantic.dev/...` 那一行，个别 JSON 输出做了紧凑排版——内容未作任何改动，你自己跑出来可能会多几行链接，属正常）。

> 💡 **关于代码块**：本书的代码块是**按顺序衔接**的（像 Jupyter Notebook 那样，一格接一格），`import` 通常只在每章开头写一次，后面的块直接复用。所以**单独复制中间某一块去跑，可能会提示某个名字未定义**——补上对应的 `from pydantic import BaseModel, Field` 之类即可，不是代码有错。

> ⚠️ **坑**：网上大量 Pydantic 教程是 V1 时代的（2023 年之前）。V1 和 V2 的 API 名字差很多（`parse_obj` → `model_validate`、`dict()` → `model_dump`、`@validator` → `@field_validator`）。看资料时先确认版本。

---

## 1. 架构总览：先看全局地图

在钻进细节之前，先建立一张全局地图。Pydantic 的世界只有 **三个动作** 和 **五个零件**。

### 1.1 三个动作：进来、待着、出去

任何数据在 Pydantic 眼里都走这条流水线：

```text
        ①  校验 (Validation)              ②  持有 (Model Instance)         ③  产出 (Serialization / Schema)
   ┌────────────────────────┐        ┌───────────────────────────┐      ┌──────────────────────────────┐
   │  外部来的"脏"数据       │        │   干净、类型正确、        │      │  model_dump()      → dict     │
   │  · HTTP 请求 JSON       │  ───▶  │   规则已保证的对象        │ ───▶ │  model_dump_json() → JSON 串  │
   │  · 数据库/Excel 行      │        │                           │      │  model_json_schema() → 说明书 │
   │  · 大模型返回的文本     │        │   代码里可以放心地用      │      │                              │
   │  · 用户表单             │        │   o.price * o.qty         │      │                              │
   └────────────────────────┘        └───────────────────────────┘      └──────────────────────────────┘
              │                                                                        │
              │  不合规 → 抛 ValidationError                                            │  说明书交给：
              ▼                                                                        ▼   · 前端渲染表单
      ┌──────────────────┐                                                       · API 文档 (OpenAPI)
      │ 一次性列出所有错误│                                                       · 大模型（结构化输出）★
      │ 定位到具体字段    │
      └──────────────────┘
```

**产品类比**：这条流水线就是「**收件 → 归档 → 出具**」。

| 流水线环节 | 产品世界的对应 |
|---|---|
| ① 校验 | 前台收材料，逐项对照清单核对，缺一样就当场退回并说清缺哪样 |
| ② 持有 | 材料入档，之后所有部门都默认这份档案是齐全、格式正确的 |
| ③ 产出 | 从档案生成对外文件：给财务的报表、给客户的回执、给新申请人的「填表须知」 |

### 1.2 五个零件：谁负责什么

```text
                          ┌─────────────────────────────────────┐
                          │            BaseModel                │
                          │      （表 / 模具 / 数据契约）        │
                          │   一个 class = 一张 PRD 字段规则表    │
                          └──────────────┬──────────────────────┘
                                         │ 由以下部件组装而成
        ┌────────────────┬───────────────┼────────────────┬──────────────────┐
        ▼                ▼               ▼                ▼                  ▼
 ┌────────────┐   ┌────────────┐  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐
 │  类型注解   │   │  Field()   │  │  校验器      │  │ model_config │  │ computed_field │
 │ Type Hints │   │ 字段元数据  │  │ Validators  │  │  ConfigDict  │  │   计算字段      │
 ├────────────┤   ├────────────┤  ├─────────────┤  ├──────────────┤  ├────────────────┤
 │ 这一列是    │   │ 这一列的    │  │ 表格填完后  │  │ 整张表的      │  │ 不用填，        │
 │ 什么类型？  │   │ 取值范围、  │  │ 还要跑的    │  │ 全局开关：    │  │ 系统自己算出来  │
 │ str/int/   │   │ 默认值、    │  │ 业务规则：  │  │ 多余字段咋办  │  │ 的列：          │
 │ 日期/枚举/ │   │ 别名、      │  │ 跨字段校验  │  │ 能不能改      │  │ 小计、是否包邮  │
 │ 嵌套表     │   │ 字段说明    │  │ 先算再判    │  │ 大小写处理    │  │                │
 └────────────┘   └────────────┘  └─────────────┘  └──────────────┘  └────────────────┘

        另有两个"表外"的工具：
 ┌──────────────────────────┐        ┌────────────────────────────────┐
 │  TypeAdapter             │        │  ValidationError               │
 │  给不是"表"的东西做校验    │        │  校验失败时的标准化错误报告      │
 │  （一个列表、一个数字）    │        │  （谁错了 / 错在哪 / 为什么错）  │
 └──────────────────────────┘        └────────────────────────────────┘
```

### 1.3 零件速查总表

先扫一眼，心里有个数，后面每一行都会开一个 `###` 小节精讲。

| 零件 | 代码长什么样 | 一句话职责 | PM 直觉对照 |
|---|---|---|---|
| **BaseModel** | `class Order(BaseModel):` | 定义一张"表"（数据契约） | PRD 里的字段规则表 / 数据库表设计 |
| **类型注解** | `price: float` | 声明这一列存什么 | Excel「单元格格式」：文本/数字/日期 |
| **Field()** | `= Field(gt=0)` | 给这一列加约束和说明 | Excel「数据验证」+ 字段备注 |
| **field_validator** | `@field_validator("code")` | 单字段的自定义规则 | 「优惠码必须以 CP 开头」这类校验 |
| **model_validator** | `@model_validator(mode="after")` | 跨字段规则 | 「结束日期必须晚于开始日期」 |
| **computed_field** | `@computed_field` | 派生出来的只读列 | Excel 公式列：小计 = 单价×数量 |
| **model_config** | `model_config = ConfigDict(...)` | 整张表的全局开关 | 表单的全局设置：是否允许多填、能否修改 |
| **model_dump / _json** | `o.model_dump()` | 把对象吐回 dict / JSON | 「导出为 Excel / CSV」 |
| **model_json_schema** | `Order.model_json_schema()` | 把表变成机器可读的说明书 ★ | 「填表须知」，给前端/大模型看 |
| **判别联合** | `Field(discriminator="type")` | 「选了 A 才出现 B 组字段」 | 表单联动 / 条件显示 |
| **ValidationError** | `except ValidationError as e:` | 标准化错误报告 | 表单提交后飘红的那一堆提示 |
| **TypeAdapter** | `TypeAdapter(list[int])` | 给非 BaseModel 的类型做校验 | 校验的不是「一张表」而是「一列数据」 |

### 1.4 一张图看懂 Pydantic 在系统里的位置

```text
  外部世界（不可信）                    │        你的系统内部（可信）
 ─────────────────────────────────────┼──────────────────────────────────────
  前端表单提交                          │
  第三方 API 回调         ┌───────────┐ │   业务逻辑代码
  数据库里的历史脏数据 ──▶ │  Pydantic  │─┼─▶ 不用再写 if x is None
  运营上传的 Excel        │   校验层   │ │   不用再写 try: int(x)
  大模型返回的 JSON  ★    └───────────┘ │   直接 order.total * 0.9
                              │         │
                              ▼         │
                        ValidationError │
                        （挡在门外）     │
```

> 👉 **PM 视角**：Pydantic 就是你系统的**前台/门卫**。它站在「不可信的外部」和「可信的内部」之间，只放行完全符合 PRD 规则的数据。这带来一个巨大的产品收益：**所有数据格式问题都在同一个地方暴露，且暴露得很早**。以前那种「用户填错了年龄，一路跑到结算模块才报个莫名其妙的错」的线上事故，本质上就是缺少这道门卫。你在评审时可以问工程师一句："这个接口的入参有没有做 schema 校验？" —— 这就是在问有没有这道门。

### 1.5 底层：为什么 Pydantic 很快

```python
import pydantic, pydantic_core
print("pydantic:", pydantic.VERSION, "| pydantic_core:", pydantic_core.__version__)
```

```text
pydantic: 2.13.4 | pydantic_core: 2.46.4
```

Pydantic 2 分成两层：你写的 Python 语法糖（`pydantic`），和真正干活的 Rust 引擎（`pydantic-core`）。所以它虽然逐字段检查，但速度很快：

```python
class P(BaseModel):
    n: int

import timeit
print("校验 10000 次耗时(秒):", round(timeit.timeit(lambda: P(n=1), number=10000), 4))
```

```text
校验 10000 次耗时(秒): 0.0059
```

一万次校验用了 6 毫秒。

> 👉 **PM 视角**：当工程师说「加这么多校验会不会拖慢接口」时，这个数据可以拿来回答。校验本身几乎不花时间，真正慢的是数据库和网络。**不要为了性能砍掉数据校验**——这是典型的省小钱花大钱。

---

## 2. BaseModel：一张表的定义

### 2.1 定义 vs 实例：模具和零件

**它解决什么问题**：把「PRD 里的字段规则表」变成代码里一个可以反复使用的东西。

```python
from datetime import date
from pydantic import BaseModel


# 这是"模具"：一次定义，描述所有 User 长什么样
class User(BaseModel):
    name: str
    age: int
    signup_date: date | None = None


# 这是"零件"：用模具做出来的一个具体实例
u = User(name="张三", age=28, signup_date="2024-03-15")
print(u)
print(repr(u.age), repr(u.signup_date))
print(type(u.signup_date))
```

```text
name='张三' age=28 signup_date=datetime.date(2024, 3, 15)
28 datetime.date(2024, 3, 15)
<class 'datetime.date'>
```

注意一个细节：我们传进去的是字符串 `"2024-03-15"`，拿出来的是一个真正的**日期对象** `datetime.date(2024, 3, 15)`。Pydantic 不只是「检查」，它还负责「转换成正确的类型」。

再看模具本身——它是可以被程序读取的：

```python
print(User.model_fields.keys())
for n, f in User.model_fields.items():
    print(n, "| required:", f.is_required(), "| default:", f.default)
```

```text
dict_keys(['name', 'age', 'signup_date'])
name | required: True | default: PydanticUndefined
age | required: True | default: PydanticUndefined
signup_date | required: False | default: None
```

`PydanticUndefined` 是 Pydantic 用来表示「压根没有默认值」的特殊标记，别把它当成一个真实的值。

> 👉 **PM 视角**：**类 = 表结构定义，实例 = 表里的一行数据**。你在 Axure 里画的那个"用户信息表单"是模具，用户每提交一次就产生一个零件。`model_fields` 这种能力更有意思：它意味着**代码里的字段规则表本身是可以被程序读出来的**。这就是为什么 Pydantic 能自动生成 API 文档、自动生成前端表单、自动生成给大模型的说明书——因为规则表不是写在注释里给人看的，而是写在代码里给机器读的。

### 2.2 三种入口：数据从哪来

**它解决什么问题**：不同来源的数据（Python 字典 / JSON 字符串 / 手写参数）都要能进这张表。

```python
# 入口 1：直接传参数（写测试、写脚本时用）
u1 = User(name="张三", age=28)

# 入口 2：从字典校验（最常用：HTTP 请求体、数据库行、Excel 行）
raw = {"name": "赵六", "age": 41, "signup_date": "2023-01-01"}
u3 = User.model_validate(raw)
print(u3)

# 入口 3：从 JSON 字符串直接校验（省掉一步 json.loads）
u4 = User.model_validate_json('{"name": "钱七", "age": 19}')
print(u4)
```

```text
name='赵六' age=41 signup_date=datetime.date(2023, 1, 1)
name='钱七' age=19 signup_date=None
```

| 方法 | 输入 | 典型场景 |
|---|---|---|
| `User(...)` | 关键字参数 | 代码里手动构造 |
| `User.model_validate(d)` | dict / 对象 | 处理请求体、数据库结果 |
| `User.model_validate_json(s)` | JSON 字符串/bytes | 直接处理 HTTP body、大模型输出 ★ |

> 👉 **PM 视角**：`model_validate_json` 是后面处理**大模型输出**的关键。大模型吐出来的是一段文本，`model_validate_json` 一步就把它变成校验过的对象——不合格式的直接报错，不会带着脏数据往下跑。

### 2.3 缺字段会怎样

**它解决什么问题**：必填项缺失时，要有明确、可读、能定位的报错，而不是程序莫名其妙崩掉。

```python
from pydantic import ValidationError

try:
    User(name="王五")     # 少了 age
except ValidationError as e:
    print(e)
```

```text
1 validation error for User
age
  Field required [type=missing, input_value={'name': '王五'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
```

这个报错包含四层信息：**哪个模型**（User）、**哪个字段**（age）、**什么问题**（Field required）、**错误码**（`missing`，可以拿来做前端多语言映射）。

> 👉 **PM 视角**：这就是你在 PRD 里写的「必填校验及错误提示文案」，只不过 Pydantic 默认给了一套英文文案 + 一个稳定的错误码。**错误码 `missing` 才是给前端用的**——前端拿到 `type: "missing"` + `loc: ["age"]`，就能在年龄输入框下面飘红显示中文文案「请填写年龄」。第 9 章会详细讲怎么读这份错误报告。

### 2.4 类型强制转换：宽进严出

**它解决什么问题**：现实世界的数据经常「类型不对但意思对」，比如表单传过来的所有值都是字符串。

```python
u2 = User(name="李四", age="30")     # 传的是字符串 "30"
print(u2)
print(type(u2.age))
```

```text
name='李四' age=30 signup_date=None
<class 'int'>
```

Pydantic 默认是**宽进严出**：能安全转换的就转换（`"30"` → `30`），转不了的才报错。第 4 章会给出完整的转换规则表。

> 👉 **PM 视角**：HTML 表单提交上来的所有字段本质上都是字符串，`age=30` 和 `age="30"` 在浏览器那头没区别。Pydantic 的自动转换省掉了大量「先转类型再判断」的胶水代码。但它有边界：`"abc"` 转不成数字就一定报错，不会悄悄变成 0。**这个"宽进"是有底线的宽进，不是和稀泥。**

### 2.5 实例的常用方法

**它解决什么问题**：拿到一个对象之后，怎么复制、怎么改、怎么知道用户到底填了哪些字段。

```python
class U(BaseModel):
    a: int
    b: str = "默认"


u = U(a=1)
print("model_fields_set:", u.model_fields_set)   # 用户"显式填了"哪些字段
u2 = u.model_copy(update={"a": 99})              # 复制一份并改几个值
print("model_copy       :", u2)
u3 = U.model_construct(a="不校验")                # 跳过校验直接造，危险
print("model_construct  :", u3)
```

```text
model_fields_set: {'a'}
model_copy       : a=99 b='默认'
model_construct  : a='不校验' b='默认'
```

| 方法 | 作用 | 注意 |
|---|---|---|
| `model_fields_set` | 用户显式传了哪些字段 | 用来区分「没填」和「填了个跟默认值一样的值」 |
| `model_copy(update={})` | 复制并局部修改 | **不会重新校验** |
| `model_construct()` | 跳过校验直接构造 | 只在「数据已确定可信」时用，比如从自己的数据库读 |

> 👉 **PM 视角**：`model_fields_set` 对应一个很常见的产品需求——**PATCH 语义**。用户在设置页把「接收推送」保持为默认的"关"，和用户主动选了"关"，业务含义可能完全不同（前者不该覆盖服务端的值，后者该覆盖）。`model_fields_set` 就是区分这两者的依据。
>
> `model_construct` 请理解为「**走绿色通道免检**」。用在内部可信数据上是性能优化，用在外部数据上是事故。

### 2.6 一个大坑：默认情况下改属性不校验

```python
u4 = User(name="钱七", age=19)
u4.age = "not a number"       # 直接赋值
print(u4.age)
```

```text
not a number
```

Pydantic 默认**只在「创建对象的那一刻」校验**。之后你往对象上乱赋值，它不管。

打开 `validate_assignment` 才会管：

```python
from pydantic import ConfigDict

class VA(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    n: int = Field(ge=0)


va = VA(n=1)
try:
    va.n = -5
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
Input should be greater than or equal to 0
```

> ⚠️ **坑**：很多人以为 Pydantic 模型是「永远合法」的，其实只有「刚出生时合法」。如果你的代码在对象创建之后还会修改字段，一定要开 `validate_assignment=True`。

> 👉 **PM 视角**：这就像**入职审核**——入职时查了学历和背景，入职以后你自己改简历系统不会再查一遍。要想「每次修改都重新审」，得单独开一个开关（而且会有一点性能成本）。

### 2.7 继承：把公共字段抽出来

**它解决什么问题**：多张表有一批共同字段（id、创建时间、创建人），不想每张表都抄一遍。

```python
class Base(BaseModel):
    id: int
    created_at: date | None = None


class Article(Base):
    title: str
    body: str = ""


a = Article(id=1, title="标题")
print(a)
print(list(Article.model_fields))
```

```text
id=1 created_at=None title='标题' body=''
['id', 'created_at', 'title', 'body']
```

子类自动拥有父类的全部字段，顺序是「父类字段在前」。

> 👉 **PM 视角**：对应 PRD 里的「**公共字段规范**」——所有业务对象都有 id、创建时间、更新时间、创建人。抽成一个 Base 就是把这个规范落到代码里，改一处所有表都跟着变。
>
> 但请记住第 6.5 节会讲的一个大坑：**继承在「校验」时很好用，在「序列化」时会咬人**。想用继承表达「A 类型 / B 类型」这种分支，正确答案是第 8 章的判别联合，不是继承。

---

## 3. Field()：给每一列加上规则和说明

`Field()` 是 Pydantic 里出场率最高的函数。它干两件事：

1. **约束**（constraint）：这一列的值必须满足什么条件 —— 对应 Excel 的「数据验证」；
2. **元数据**（metadata）：这一列叫什么、什么意思、默认值、别名 —— 对应字段备注和文档。

### 3.1 数值约束：gt / ge / lt / le

**它解决什么问题**：「价格必须大于 0」「打分必须在 1–5 之间」这类范围规则。

```python
from pydantic import BaseModel, Field, ValidationError


class Product(BaseModel):
    price: float = Field(gt=0, le=99999)      # 大于 0，小于等于 99999
    stock: int = Field(ge=0, default=0)       # 大于等于 0，默认 0
```

| 参数 | 全称 | 含义 | 数学符号 |
|---|---|---|---|
| `gt` | greater than | 大于 | `>` |
| `ge` | greater than or equal | 大于等于 | `≥` |
| `lt` | less than | 小于 | `<` |
| `le` | less than or equal | 小于等于 | `≤` |
| `multiple_of` | — | 必须是某数的整数倍 | 步长 |

```python
try:
    Product(price=-5, stock=-1)
except ValidationError as e:
    print(e)
```

```text
2 validation errors for Product
price
  Input should be greater than 0 [type=greater_than, input_value=-5, input_type=int]
    For further information visit https://errors.pydantic.dev/2.13/v/greater_than
stock
  Input should be greater than or equal to 0 [type=greater_than_equal, input_value=-1, input_type=int]
    For further information visit https://errors.pydantic.dev/2.13/v/greater_than_equal
```

注意：**两个错误一次性全报出来了**，不是报完第一个就停。

> 👉 **PM 视角**：`gt=0` 和 `ge=0` 的区别就是「必须大于零」和「可以是零」——这个在 PRD 里经常被写含糊。「库存不能为负」是 `ge=0`（0 是合法的，代表卖光了）；「价格必须为正」是 `gt=0`（0 元商品要走另一套逻辑）。**把这两个词分清楚，能少掉一半的联调扯皮。**
>
> 另外注意「一次性报出所有错误」这个行为。这直接决定了前端体验：是一次飘红全部错误（用户改一遍就好），还是改一个报一个（用户要提交五次）。Pydantic 默认是前者。

### 3.2 字符串约束：min_length / max_length / pattern

**它解决什么问题**：「昵称 2–20 字」「手机号 11 位 1 开头」这类文本规则。

```python
class Product2(BaseModel):
    sku: str = Field(min_length=6, max_length=12)
    title: str = Field(max_length=30, description="商品标题，展示在列表页")
    phone: str = Field(pattern=r"^1\d{10}$")     # 正则：1 开头 + 10 位数字
```

```python
try:
    Product2(sku="A1", title="x" * 40, phone="13800138000")
except ValidationError as e:
    print(e)
```

```text
sku
  String should have at least 6 characters [type=string_too_short, input_value='A1', input_type=str]
title
  String should have at most 30 characters [type=string_too_long, input_value='xxxx...', input_type=str]
```

正则不匹配的报错：

```python
try:
    Product2(sku="ABC123", title="正常标题", phone="123")
except ValidationError as e:
    print(e)
```

```text
1 validation error for Product2
phone
  String should match pattern '^1\d{10}$' [type=string_pattern_mismatch, input_value='123', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/string_pattern_mismatch
```

> 👉 **PM 视角**：`pattern` 就是 Excel 数据验证里的「自定义公式」，也是前端表单里那条正则。**关键提醒：前端的正则和后端的正则必须是同一条**，否则会出现「前端让过后端拒绝」这种最气人的 bug。理想做法是后端定义一次，通过 JSON Schema（第 7 章）自动同步给前端——`pattern` 会原样出现在 schema 里。

### 3.3 字符串的进阶处理：StringConstraints

**它解决什么问题**：不只是「检查」，还要「顺手清洗」——去空格、转大写、转小写。

`Field()` 表达不了这类需求，要用 `StringConstraints`：

```python
from typing import Annotated
from pydantic import BaseModel, StringConstraints


class Form(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True)]


print(Form(code="  ab12 ").code)
```

```text
AB12
```

| 参数 | 作用 |
|---|---|
| `strip_whitespace=True` | 去掉首尾空格 |
| `to_upper=True` / `to_lower=True` | 转大写 / 小写 |
| `min_length` / `max_length` / `pattern` | 同 `Field()` |

> 👉 **PM 视角**：这对应产品里一条经常被忽略、但线上一定会出事的规则——**用户输入的首尾空格**。用户复制粘贴优惠码时几乎必然会带上空格；邮箱输成 `Foo@Bar.com` 也应该和 `foo@bar.com` 视为同一个。与其在 PRD 里写「前端做 trim」，不如让后端在校验层统一 trim。**清洗规则应该属于数据契约，而不是属于某个端。**

### 3.4 集合约束：min_length / max_length 用在列表上

**它解决什么问题**：「购物车至少 1 件、最多 20 件」「标签最多选 3 个」这类数量规则。

同样的 `min_length` / `max_length`，挂在列表上时管的是**元素个数**，不是字符数。

```python
class Cart(BaseModel):
    items: list[str] = Field(min_length=1, max_length=20, description="购物车明细")
    tags: list[str] = Field(default_factory=list, max_length=3)


try:
    Cart(items=[], tags=["a", "b", "c", "d"])
except ValidationError as e:
    print(e)
```

```text
2 validation errors for Cart
items
  List should have at least 1 item after validation, not 0 [type=too_short, input_value=[], input_type=list]
    For further information visit https://errors.pydantic.dev/2.13/v/too_short
tags
  List should have at most 3 items after validation, not 4 [type=too_long, input_value=['a', 'b', 'c', 'd'], input_type=list]
    For further information visit https://errors.pydantic.dev/2.13/v/too_long
```

> 👉 **PM 视角**：「购物车不能为空」「标签最多选 3 个」「一次最多批量导入 1000 条」——这些全是集合长度约束。写 PRD 时把上限写出来很重要，它同时是**产品规则**和**防止被刷的保护**。

### 3.5 默认值：default 和 default_factory

**它解决什么问题**：字段不填时给一个兜底值。

```python
from datetime import datetime
import uuid


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: datetime = Field(default_factory=datetime.now)
    tags: list[str] = Field(default_factory=list)
    status: str = "pending"          # 简单常量，直接写等号就行


o1 = Order()
o2 = Order()
print(o1.order_id != o2.order_id, "两次生成的 id 不同")
o1.tags.append("vip")
print("o1.tags:", o1.tags, "o2.tags:", o2.tags)
```

```text
True 两次生成的 id 不同
o1.tags: ['vip'] o2.tags: []
```

| 写法 | 用于 | 例子 |
|---|---|---|
| `= "pending"` | 固定不变的常量 | 状态默认值、开关默认关 |
| `Field(default_factory=...)` | **每次都要重新算**的值 | 当前时间、随机 ID、空列表 |

> ⚠️ **坑**：可变类型（列表、字典）的默认值**必须**用 `default_factory=list` / `default_factory=dict`。上面的输出证明了 `o1` 加标签不会污染 `o2`——如果写成共享的一个列表，所有订单会共用同一个标签列表，这是 Python 里最经典的 bug 之一。（Pydantic 其实对 `= []` 做了保护性拷贝，但显式写 `default_factory` 是更稳妥、也更表意的写法。）

> 👉 **PM 视角**：`default` 和 `default_factory` 的区别，等价于 PRD 里「**默认值**」和「**默认生成规则**」的区别。「订单状态默认为待支付」是常量；「订单号自动生成」「创建时间取当前时间」是规则。写 PRD 时把「自动生成」的字段单独列一节，工程师就知道要用 `default_factory`。

### 3.6 「看起来有默认值，其实是必填」的经典坑

```python
class Bad(BaseModel):
    a: int = Field(description="看起来像有默认值，其实是必填")


try:
    Bad()
except ValidationError as e:
    print(e)
```

```text
1 validation error for Bad
a
  Field required [type=missing, input_value={}, input_type=dict]
```

`a: int = Field(...)` 里那个等号**不是默认值**，它只是把 `Field()` 这个"配置包"挂到字段上。没写 `default=` 就仍然是必填。

> ⚠️ **坑**：这是 Pydantic 新手最常踩的坑。看到等号就以为是选填，结果线上一直报 `missing`。

推荐用 `Annotated` 写法避免歧义：

```python
from typing import Annotated

class Good(BaseModel):
    a: Annotated[int, Field(description="必填，一眼看得出")]          # 必填
    b: Annotated[int, Field(ge=0, description="选填")] = 1           # 有等号 = 选填

try:
    Good()
except ValidationError as e:
    print("Good 同样必填:", e.errors()[0]["type"])
```

```text
Good 同样必填: missing
```

### 3.7 两种写法：赋值形式 vs Annotated 形式

**它解决什么问题**：同一个 `Field()` 有两种挂法，什么时候用哪种。

```python
# 写法 A：赋值形式（assignment form）
class M1(BaseModel):
    price: float = Field(gt=0, description="单价")

# 写法 B：Annotated 形式（annotated pattern）
class M2(BaseModel):
    price: Annotated[float, Field(gt=0, description="单价")]
```

| 对比项 | 赋值形式 `x: T = Field(...)` | Annotated 形式 `x: Annotated[T, Field(...)]` |
|---|---|---|
| 可读性 | 简短，最常见 | 略啰嗦 |
| 必填/选填是否一目了然 | ❌ 有歧义（见 3.6） | ✅ 有等号才是选填 |
| 能否叠加多个元数据 | 只能一个 `Field()` | ✅ 可以叠很多个 |
| `default` / `default_factory` / `alias` | ✅ **应该用这个** | ⚠️ 类型检查器不认 |
| 类型别名可复用 | ❌ | ✅ `Score = Annotated[int, Field(ge=0, le=100)]` |

Annotated 可以叠加多个约束来源：

```python
from annotated_types import Gt, Le

class M(BaseModel):
    score: Annotated[int, Gt(0), Le(100), Field(description="0-100 分")]


print(M(score=88))
try:
    M(score=101)
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
score=88
Input should be less than or equal to 100
```

**实用建议**：
- 默认值、别名 → 用赋值形式（`= Field(default=..., alias=...)`）；
- 想把「一类字段的规则」复用到多个地方 → 定义一个 `Annotated` 类型别名。

复用示例：

```python
Score = Annotated[int, Field(ge=0, le=100, description="0-100 分")]

class Exam(BaseModel):
    chinese: Score
    math: Score
    english: Score
```

> 👉 **PM 视角**：`Annotated` 类型别名 = PRD 里的「**字段字典 / 数据元定义**」。大公司都会维护一份「手机号的标准定义」「金额的标准定义」，然后各个模块引用它，而不是各写各的。`Score = Annotated[int, Field(ge=0, le=100)]` 就是把这份字段字典写进了代码，改一次全局生效。

> ⚠️ **坑**：字段专属的元数据（`alias`、`deprecated`）必须挂在**最外层类型**上。下面这两行差别很大：
>
> ```python
> class M(BaseModel):
>     field_bad: Annotated[int, Field(deprecated=True)] | None = None   # 无效
>     field_ok: Annotated[int | None, Field(deprecated=True)] = None    # 有效
> ```
>
> 实际运行 2.13.4 会直接给出警告：
> ```text
> UnsupportedFieldAttributeWarning: The 'deprecated' attribute with value True was provided to
> the `Field()` function, which has no effect in the context it was used.
> ```
> 读 `field_bad` 不会有弃用警告，读 `field_ok` 才会。区别在于 `Field()` 是套在整个 `int | None` 外面，还是只套在 `int` 上。

### 3.8 description：给字段写说明

**它解决什么问题**：让这一列的业务含义写在代码里，并且能被自动导出成文档。

```python
class Feedback(BaseModel):
    score: int = Field(ge=1, le=5, description="满意度打分，1 最差 5 最好")
```

`description` 不参与校验，但它会**原样出现在 JSON Schema 里**（第 7 章会看到）。

> 👉 **PM 视角**：**这是整篇教程里，产品经理最应该关心的一个参数。**
>
> `description` 是你写的那句业务说明的唯一栖身之所。它会流向三个地方：
> 1. 自动生成的 API 文档 → 前端和第三方看的；
> 2. 自动生成的表单提示 → 用户看的；
> 3. **给大模型的提示 → 决定模型填得对不对** ★
>
> 第三点是本书后面的重头戏。当你用 Pydantic AI 让模型「从这段对话里提取用户诉求」时，模型看到的就是你写的 `description`。**`description` 写得含糊，模型就填得含糊**。它已经不是「注释」了，它是提示词的一部分。评审时值得专门看一眼这些字段说明写得好不好。

### 3.9 alias：字段的对外名字

**它解决什么问题**：内部字段名和外部接口字段名不一致（内部 `user_name`，接口是 `userName`）。

```python
class ApiUser(BaseModel):
    user_name: str = Field(alias="userName")
    is_vip: bool = Field(alias="isVIP", default=False)


au = ApiUser.model_validate({"userName": "tom", "isVIP": True})
print(au)                              # 内部用蛇形命名
print(au.model_dump())                 # 默认按内部名字导出
print(au.model_dump(by_alias=True))    # 按外部名字导出
```

```text
user_name='tom' is_vip=True
{'user_name': 'tom', 'is_vip': True}
{'userName': 'tom', 'isVIP': True}
```

> ⚠️ **坑**：设了 `alias` 之后，**默认只认外部名字**：

```python
try:
    ApiUser(user_name="tom")
except ValidationError as e:
    print(e)
```

```text
1 validation error for ApiUser
userName
  Field required [type=missing, input_value={'user_name': 'tom'}, input_type=dict]
```

想两种都认，加配置 `populate_by_name=True`（**注意**：Pydantic 2.11+ 起官方更推荐等价的 `ConfigDict(validate_by_name=True, validate_by_alias=True)`，`populate_by_name` 计划在 v3 废弃，新项目建议直接用新写法）：

```python
class ApiUser2(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_name: str = Field(alias="userName")


print(ApiUser2(user_name="tom"))
print(ApiUser2(userName="jerry"))
```

```text
user_name='tom'
user_name='jerry'
```

**进出可以用不同名字**：

```python
class Split(BaseModel):
    n: str = Field(validation_alias="inputName", serialization_alias="outputName")


s = Split.model_validate({"inputName": "x"})
print(s.model_dump(), s.model_dump(by_alias=True))
```

```text
{'n': 'x'} {'outputName': 'x'}
```

**兼容多个上游字段名**（老接口叫 `uid`，新接口叫 `userId`）：

```python
from pydantic import AliasChoices

class Compat(BaseModel):
    user_id: int = Field(validation_alias=AliasChoices("uid", "userId", "user_id"))


for k in ["uid", "userId", "user_id"]:
    print(k, "->", Compat.model_validate({k: 7}))
```

```text
uid -> user_id=7
userId -> user_id=7
user_id -> user_id=7
```

| 参数 | 管什么 |
|---|---|
| `alias` | 进和出都用这个名字 |
| `validation_alias` | 只管「进来时」认什么名字 |
| `serialization_alias` | 只管「出去时」叫什么名字 |
| `AliasChoices(...)` | 进来时接受多个候选名字 |

> 👉 **PM 视角**：alias 对应的是**系统对接时的字段映射表**。做过 ERP 对接、支付渠道对接、数据中台接入的 PM 都很熟悉那张 Excel：「我方字段 / 对方字段 / 转换规则」。alias 就是把那张映射表写进代码。
>
> `AliasChoices` 尤其对应一个真实场景：**接口版本升级过渡期**。老 App 还在传 `uid`，新 App 传 `userId`，服务端两个都得认，直到老版本用户量降到可以下线为止。这在 PRD 里叫「向后兼容」，在代码里就是这一行。

### 3.10 examples：给字段举例

```python
class P(BaseModel):
    sku: str = Field(description="商品编码", examples=["SKU-001", "SKU-002"],
                     json_schema_extra={"x-internal": True})
```

生成的 schema 片段：

```json
{
  "sku": {
    "description": "商品编码",
    "examples": ["SKU-001", "SKU-002"],
    "title": "Sku",
    "type": "string",
    "x-internal": true
  }
}
```

`json_schema_extra` 可以往说明书里塞任何自定义的键（比如给内部工具用的标记）。

> 👉 **PM 视角**：`examples` 会流进 API 文档，也会流进给大模型的说明书。**给大模型举一个例子，往往比写三行描述更有效**——这是提示词工程里的 few-shot 思想，在这里只需要填一个参数。

---

## 4. 类型系统：这一列到底能填什么

类型注解是 Pydantic 的地基。这一章把常用类型逐个讲清楚。

### 4.0 类型分类总表

| 分类 | 代表写法 | 对应 Excel/表单里的什么 |
|---|---|---|
| 基础标量 | `str` `int` `float` `bool` | 文本 / 整数 / 小数 / 复选框 |
| 时间 | `date` `datetime` `time` `timedelta` | 日期选择器 |
| 精确数字 | `Decimal` | 金额（不能有浮点误差） |
| 可空 | `str \| None` | 允许留空的单元格 |
| 固定选项 | `Literal["A","B"]` / `Enum` | 下拉框 |
| 嵌套 | `Address`（另一个 BaseModel） | 子表 / 明细表 |
| 集合 | `list[X]` `dict[str,X]` `set[X]` `tuple[X,Y]` | 多行明细 / 键值对 / 去重列表 |
| 网络类型 | `HttpUrl` `EmailStr` `IPvAnyAddress` | 带格式校验的特殊输入框 |
| 分支 | `Annotated[A \| B, Field(discriminator=...)]` | 联动表单（第 8 章） |
| 任意 | `Any` | 不做校验的自由字段 |

### 4.1 基础类型与强制转换规则

**它解决什么问题**：外部数据类型总是不规整，需要一套明确的「什么能转、什么不能转」的规则。

```python
from decimal import Decimal
from datetime import date, datetime


class Coerce(BaseModel):
    i: int
    f: float
    b: bool
    s: str
    d: date
    dt: datetime
    dec: Decimal


x = Coerce(i="42", f="3.14", b="yes", s="hello", d="2024-01-01",
           dt="2024-01-01T10:30:00", dec="19.99")
print(x)
```

```text
i=42 f=3.14 b=True s='hello' d=datetime.date(2024, 1, 1) dt=datetime.datetime(2024, 1, 1, 10, 30) dec=Decimal('19.99')
```

哪些转不了：

```text
  i='abc' -> 失败: Input should be a valid integer, unable to parse string as an integer
  i=3.7   -> 失败: Input should be a valid integer, got a number with a fractional part
  s=123   -> 失败: Input should be a valid string
  b='maybe' -> 失败: Input should be a valid boolean, unable to interpret input
```

**转换规则速查**：

| 目标类型 | 接受 | 拒绝 |
|---|---|---|
| `int` | `"42"`、`42.0` | `"abc"`、`3.7`（有小数部分，怕丢精度） |
| `float` | `"3.14"`、`3`、`Decimal` | `"abc"` |
| `str` | 只接受字符串 | **数字 `123` 会被拒**（防止意外把 ID 变成字符串） |
| `bool` | `1/0`、`"true"/"false"`、`"yes"/"no"`、`"on"/"off"`、`"1"/"0"` | `2`、`"maybe"` |
| `date` | `"2024-01-01"`、时间戳 | `"2024/13/45"` |
| `Decimal` | `"19.99"`、数字 | 非数字文本 |

`bool` 到底认哪些值，实测一遍：

```text
  1 -> True        0 -> False
  'true' -> True   'True' -> True
  'yes' -> True    'on' -> True
  '1' -> True      '0' -> False
  'no' -> False
  2 -> 报错
```

> ⚠️ **坑**：`int` 字段拒绝 `3.7`，但接受 `42.0`。逻辑是「不能丢信息」。同理，`str` 字段拒绝数字 `123`，因为 Pydantic 认为「你声明了是文本，传数字八成是上游搞错了」。

> 👉 **PM 视角**：这张表就是你和工程师之间关于「**脏数据怎么办**」的默认约定。请特别注意 `bool` 那一行——运营从 Excel 导数据时，「是/否」列里可能填 `1`、`是`、`Y`、`true`、`TRUE`，Pydantic 只认最后几种。**`"是"` 和 `"Y"` 是不认的**。这意味着导入功能的 PRD 里必须明确写清楚「布尔列接受哪些写法」，否则运营导一次挂一次。
>
> 还有 `Decimal`：**只要是钱，就该用 `Decimal` 而不是 `float`**。`float` 存 0.1 + 0.2 会得到 0.30000000000000004，做金额累加会出现一分钱对不上账的事故。这条值得写进你们团队的字段规范。

### 4.2 Optional：可空 ≠ 选填

**它解决什么问题**：区分「这个字段可以不传」和「这个字段可以传空值」——它们在产品上是两件事。

```python
class A(BaseModel):
    a: str | None          # 必填，但值可以是 None
    b: str | None = None   # 选填，不传就是 None
    c: str = "默认值"       # 选填，不传就是"默认值"


print(A(a=None))
try:
    A()                    # 只有 a 会报错
except ValidationError as e:
    print([(x["loc"], x["type"]) for x in e.errors()])
```

```text
a=None b=None c='默认值'
[(('a',), 'missing')]
```

| 写法 | 必填？ | 能传 None？ | 产品含义 |
|---|---|---|---|
| `x: str` | ✅ 必填 | ❌ | 必填且必须有值 |
| `x: str \| None` | ✅ 必填 | ✅ | **必须表态**，但可以表态为"无" |
| `x: str \| None = None` | ❌ 选填 | ✅ | 可以不管它 |
| `x: str = "默认值"` | ❌ 选填 | ❌ | 不管它就用默认 |

`Optional[str]` 和 `str | None` 完全等价，是老写法：

```python
from typing import Optional

class O(BaseModel):
    x: Optional[str]   # 仍然是必填！


try:
    O()
except ValidationError as e:
    print(e.errors()[0]["type"], e.errors()[0]["loc"])
print(O(x=None))
```

```text
missing ('x',)
x=None
```

> ⚠️ **坑**：`Optional` 这个词起得非常有误导性。它的意思是「**值可以为空**」，不是「**可以不填**」。要「可以不填」必须再加 `= None`。

> 👉 **PM 视角**：第二行 `x: str | None`（必填但可为 None）对应一个很有价值的产品设计——**强制表态**。比如问卷里的「是否有过敏史」，你不能让用户跳过，但允许他选「无」。「没填」和「填了没有」是两种完全不同的数据质量。
>
> 反过来，如果你在 PRD 里只写「选填」，工程师大概率写成第三行。**「选填」「可为空」「有默认值」这三个词，在需求评审时要说清楚是哪一个。**

### 4.3 Literal：写死的几个选项

**它解决什么问题**：下拉框——这个字段只能是这几个值之一。

```python
from typing import Literal


class Ticket(BaseModel):
    priority: Literal["P0", "P1", "P2"]
    channel: Literal["app", "web", "wechat"] = "app"


print(Ticket(priority="P0"))
try:
    Ticket(priority="紧急")
except ValidationError as e:
    print(e)
```

```text
priority='P0' channel='app'
1 validation error for Ticket
priority
  Input should be 'P0', 'P1' or 'P2' [type=literal_error, input_value='紧急', input_type=str]
```

注意错误信息 `Input should be 'P0', 'P1' or 'P2'`——它**自动把所有合法选项列出来了**。

> 👉 **PM 视角**：`Literal` 就是**下拉框 / 单选按钮组**，对应 Excel 数据验证里的「序列」。用 `str` 表示状态是个坏习惯——那等于给了个自由文本框，运营写 "已完成"、"完成"、"done"、"DONE" 全都能存进去，最后统计口径全乱。
>
> 而且 `Literal` 有个额外好处：**选项列表会自动进入 JSON Schema，变成下拉框选项，也变成给大模型的可选值清单**（第 7 章）。这意味着你在 PRD 里定义的枚举值，会一路自动流到前端和 AI，不需要三个地方各维护一份。

### 4.4 Enum：给选项起名字

**它解决什么问题**：选项多、要复用、要在代码里用名字引用时，`Literal` 不够用。

```python
from enum import Enum


class Status(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Post(BaseModel):
    status: Status


p = Post(status="published")
print(p, "|", p.status is Status.PUBLISHED)
print(p.model_dump())
print(p.model_dump(mode="json"))
```

```text
status=<Status.PUBLISHED: 'published'> | True
{'status': <Status.PUBLISHED: 'published'>}
{'status': 'published'}
```

| 对比 | `Literal` | `Enum` |
|---|---|---|
| 写起来 | 简单，一行 | 要单独定义一个类 |
| 复用 | 复制粘贴 | ✅ 一处定义多处引用 |
| 代码里引用 | 只能写字符串 `"published"` | ✅ `Status.PUBLISHED` |
| 出 JSON Schema | `enum: [...]` | `enum: [...]`（多一层 `$ref`） |
| 序列化 | 直接是字符串 | 默认是枚举对象，`mode="json"` 才变字符串 |

> ⚠️ **坑**：`model_dump()` 默认给你的是**枚举对象**不是字符串。要么用 `model_dump(mode="json")`，要么开配置 `use_enum_values=True`（见 10.6）。

> 👉 **PM 视角**：选项少且只在一处用 → `Literal`；选项要在多个模块间共享、且有「业务名字」（如「订单状态机」的各个状态）→ `Enum`。后者更像是 PRD 里那张单独成节的「**状态枚举定义表**」，值得给每个状态起个正式名字。

### 4.5 嵌套模型：表里套表

**它解决什么问题**：一个业务对象里包含另一个业务对象——订单里有收货地址，客户下面有多个联系人。

```python
class Address(BaseModel):
    province: str
    city: str
    detail: str


class Contact(BaseModel):
    name: str
    phone: str = Field(pattern=r"^1\d{10}$")


class Customer(BaseModel):
    name: str
    address: Address                                   # 一对一
    contacts: list[Contact] = Field(default_factory=list)   # 一对多


c = Customer.model_validate({
    "name": "字节跳动",
    "address": {"province": "北京", "city": "北京", "detail": "海淀区"},
    "contacts": [{"name": "小王", "phone": "13800138000"}],
})
print(c)
print(c.address.city, c.contacts[0].name)
```

```text
name='字节跳动' address=Address(province='北京', city='北京', detail='海淀区') contacts=[Contact(name='小王', phone='13800138000')]
北京 小王
```

嵌套的报错会**精确定位到层级**：

```python
try:
    Customer.model_validate({
        "name": "X",
        "address": {"province": "北京", "city": "北京"},        # 少 detail
        "contacts": [{"name": "小王", "phone": "123"}],         # 手机号不对
    })
except ValidationError as e:
    print(e)
```

```text
2 validation errors for Customer
address.detail
  Field required [type=missing, input_value={'province': '北京', 'city': '北京'}, input_type=dict]
contacts.0.phone
  String should match pattern '^1\d{10}$' [type=string_pattern_mismatch, input_value='123', input_type=str]
```

`contacts.0.phone` = 「contacts 列表里第 0 个元素的 phone 字段」。

> 👉 **PM 视角**：嵌套模型 = **主表 + 子表**。订单（主表）+ 订单明细（子表）是最经典的例子。
>
> 特别注意错误定位 `contacts.0.phone`。这在产品上非常有用：用户批量导入 100 行数据，其中第 37 行的手机号格式不对，报错能精确告诉你「第 37 行的 phone 列」，而不是笼统一句「导入失败」。**批量导入功能的错误提示做得好不好，很大程度上就取决于有没有用好这个定位信息。**

### 4.6 自引用：树形结构

**它解决什么问题**：分类树、组织架构、评论盖楼——一个节点下面还是同类节点。

```python
class Category(BaseModel):
    name: str
    children: list["Category"] = []      # 引用自己，要加引号


c = Category.model_validate({
    "name": "电子产品",
    "children": [{"name": "手机", "children": [{"name": "安卓机"}]}],
})
print(c.model_dump())
```

```text
{'name': '电子产品', 'children': [{'name': '手机', 'children': [{'name': '安卓机', 'children': []}]}]}
```

> 👉 **PM 视角**：类目树、部门树、权限树、多级评论——所有「无限层级」的产品结构都是这个模型。Pydantic 会**递归校验每一层**，所以一棵歪掉的树在入口处就会被挡住。

### 4.7 集合类型

**它解决什么问题**：一个字段要装多个值，且对「是否去重、是否有序、能否重复」有要求。

```python
class Coll(BaseModel):
    tags: list[str]           # 有序、可重复
    unique_ids: set[int]      # 无序、自动去重
    scores: dict[str, float]  # 键值对
    point: tuple[int, int]    # 定长、位置有含义


cc = Coll(tags=("a", "b"), unique_ids=[1, 2, 2, 3],
          scores={"math": "90.5"}, point=[1, 2])
print(cc)
print(type(cc.tags), type(cc.unique_ids))
```

```text
tags=['a', 'b'] unique_ids={1, 2, 3} scores={'math': 90.5} point=(1, 2)
<class 'list'> <class 'set'>
```

三个观察点：
1. 传进去是元组 `("a","b")`，出来是列表——Pydantic 按你**声明的类型**转换；
2. `set[int]` 自动把 `[1,2,2,3]` 去重成 `{1,2,3}`；
3. 集合内部的元素**也会被校验和转换**（`"90.5"` → `90.5`）。

| 类型 | 有序 | 可重复 | 典型用途 |
|---|---|---|---|
| `list[X]` | ✅ | ✅ | 订单明细、操作日志 |
| `set[X]` | ❌ | ❌ 自动去重 | 标签集合、权限集合 |
| `dict[str, X]` | — | 键唯一 | 配置项、多语言文案 |
| `tuple[X, Y]` | ✅ | 定长 | 坐标、区间 `(min, max)` |

> 👉 **PM 视角**：选 `list` 还是 `set` 是**一个产品决策，不是技术细节**。
> - 「用户选了哪些标签」→ `set`，因为选两次同一个标签应该只算一次；
> - 「用户的浏览历史」→ `list`，因为顺序有意义，重复访问也有意义。
>
> 你在 PRD 里如果只写「标签列表」，工程师会用 `list`，然后就会出现"同一个标签出现两次"的 bug。**明确写「去重」两个字**。

### 4.8 特殊类型：URL、邮箱

**它解决什么问题**：常见的格式校验不用自己写正则。

```python
from pydantic import HttpUrl, EmailStr


class Special(BaseModel):
    url: HttpUrl
    email: EmailStr


sp = Special(url="https://example.com/path", email="a@b.com")
print(sp)
print(sp.model_dump(mode="json"))
```

```text
url=HttpUrl('https://example.com/path') email='a@b.com'
{'url': 'https://example.com/path', 'email': 'a@b.com'}
```

Pydantic 内置了一批这类类型：`HttpUrl`、`AnyUrl`、`EmailStr`、`IPvAnyAddress`、`UUID4`、`PositiveInt`、`NonNegativeFloat`、`SecretStr` 等。

> ⚠️ **坑**：`EmailStr` 需要额外安装 `pydantic[email]`，否则会报错让你装 `email-validator`。

> 👉 **PM 视角**：邮箱格式的正则是出了名的难写对（合法邮箱的规则比大多数人想的复杂得多）。用内置类型意味着**这条规则由库来维护，不由你的工程师维护**。
>
> 顺便提一个 `SecretStr`：它在打印日志时会显示成 `**********`，防止密码、密钥被打进日志。**这是「日志脱敏」这条合规要求在代码里的落点**，做金融、医疗类产品的 PM 可以专门问一句。

### 4.9 严格模式：不许自动转换

**它解决什么问题**：某些字段宁可报错也不能猜。

```python
class S(BaseModel):
    n: Annotated[int, Field(strict=True)]


try:
    S(n="42")
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
Input should be a valid integer
```

> 👉 **PM 视角**：默认的宽松转换在 90% 场景下是省事的，但在**金额、账号、订单号**这类字段上，「猜」是危险的。开 `strict=True` 相当于告诉系统：这一列必须是上游明确按类型传过来的，我不接受任何形式的自动理解。

---

## 5. 校验器：写不出来的规则，自己写

`Field()` 能表达的是「通用约束」（大于、小于、长度、正则）。但业务规则往往更复杂：

- 「优惠券码必须以 CP 开头」→ 单字段自定义规则
- 「活动结束时间必须晚于开始时间」→ 跨字段规则
- 「订单总额（自己算出来的）超过 5 万要走审批」→ 先算再判

这三类分别对应 `field_validator`、`model_validator`，以及两者的组合。

### 5.0 校验器分类总表

| 类型 | 装饰器 | 管几个字段 | 拿到的是什么 | 典型场景 |
|---|---|---|---|---|
| 字段-前置 | `@field_validator("x", mode="before")` | 1 个 | **原始输入**，什么都可能是 | 清洗脏数据（去 `¥`、去逗号） |
| 字段-后置 | `@field_validator("x", mode="after")` | 1 个 | **已转好类型**的值 | 业务规则判断（默认，推荐） |
| 模型-前置 | `@model_validator(mode="before")` | 全部 | **原始 dict** | 结构改造（打平嵌套、兼容老格式） |
| 模型-后置 | `@model_validator(mode="after")` | 全部 | **已构造好的模型对象** | 跨字段校验、算派生值（推荐） |
| 注解式 | `Annotated[int, AfterValidator(fn)]` | 1 个 | 同后置 | 规则要复用到多个字段时 |

### 5.1 field_validator：单字段自定义规则

**它解决什么问题**：这一列有个业务规则，正则和数值范围都表达不了。

```python
from pydantic import BaseModel, ValidationError, field_validator


class Coupon(BaseModel):
    code: str

    @field_validator("code", mode="after")
    @classmethod
    def code_prefix(cls, v: str) -> str:
        v = v.strip().upper()          # 先规整
        if not v.startswith("CP"):     # 再判断
            raise ValueError("优惠券码必须以 CP 开头")
        return v                       # 记得把处理后的值还回去


print(Coupon(code="cp2024"))
try:
    Coupon(code="XX001")
except ValidationError as e:
    print(e)
```

```text
code='CP2024'
1 validation error for Coupon
code
  Value error, 优惠券码必须以 CP 开头 [type=value_error, input_value='XX001', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/value_error
```

三个必须记住的规则：

1. **应该加 `@classmethod`（不加也能跑，但类型检查器会报错，官方示例统一这么写）**，且顺序是 `@field_validator` 在上、`@classmethod` 在下；
2. **必须 `return` 那个值**——忘了 return，字段会变成 `None`；
3. 抛 `ValueError`（不是别的异常），Pydantic 会把它包装成标准的 `ValidationError`。

> ⚠️ **坑**：注意上面代码里的顺序——**先 `.upper()` 再判断 `startswith("CP")`**。如果先判断再转大写，用户输入 `cp2024`（小写）就会被拒绝。这是写校验器时最容易出的逻辑错误：清洗和判断的顺序搞反了。

> 👉 **PM 视角**：`field_validator` 对应 PRD 里那种「**除了格式，还有业务含义**」的规则。比如「身份证号要通过校验位算法」「银行卡号要过 Luhn 校验」「优惠券码前两位是渠道标识」。
>
> 更重要的是那句错误文案 `优惠券码必须以 CP 开头`——**这是唯一可以由你（PM）直接决定的用户可见文案**。内置约束的文案是英文的，自定义校验器的文案是你写的。所以在 PRD 里写自定义校验规则时，**把提示文案一起写上**。

### 5.2 mode="before" vs mode="after"：拿到的东西不一样

**它解决什么问题**：搞清楚校验器在流水线的哪个位置执行，决定了你能拿到什么、能干什么。

```python
class Demo(BaseModel):
    n: int

    @field_validator("n", mode="before")
    @classmethod
    def show_before(cls, v):
        print(f"  before 拿到: {v!r} ({type(v).__name__})")
        return v

    @field_validator("n", mode="after")
    @classmethod
    def show_after(cls, v: int) -> int:
        print(f"  after  拿到: {v!r} ({type(v).__name__})")
        return v


Demo(n="123")
```

```text
  before 拿到: '123' (str)
  after  拿到: 123 (int)
```

一图看懂位置：

```text
   原始输入 "123"
       │
       ▼
  ┌─────────────┐
  │ before 校验器│   ← 拿到 '123'（字符串），可以是任何东西
  └─────────────┘
       │
       ▼
  ┌─────────────┐
  │ 类型转换 +   │   ← Pydantic 内置的转换和约束检查
  │ 内置约束     │
  └─────────────┘
       │
       ▼
  ┌─────────────┐
  │ after 校验器 │   ← 拿到 123（整数），类型已保证
  └─────────────┘
       │
       ▼
    最终字段值
```

**`before` 的典型用途：清洗脏数据**

```python
class Money(BaseModel):
    amount: float

    @field_validator("amount", mode="before")
    @classmethod
    def clean(cls, v):
        if isinstance(v, str):
            return v.replace("¥", "").replace(",", "").strip()
        return v


print(Money(amount="¥1,299.00"))
```

```text
amount=1299.0
```

如果没有这个 `before` 校验器，`"¥1,299.00"` 会直接因为无法转成 float 而报错。

| | `before` | `after` |
|---|---|---|
| 执行时机 | 类型转换**之前** | 类型转换**之后** |
| 拿到的值 | 原始输入，类型不确定 | 已转好类型 |
| 主要用途 | **改造/清洗**输入 | **判断**业务规则 |
| 风险 | 高（要自己处理各种类型） | 低 |
| 推荐度 | 需要时才用 | ✅ 默认用这个 |

> 👉 **PM 视角**：这两个模式对应产品里两个不同的动作——**「预处理」和「审核」**。
>
> - `before` = 收件时的**整理**：把用户粘贴过来的 `¥1,299.00` 变成 `1299.00`，把 Excel 里的全角逗号换成半角。这是"帮用户一把"。
> - `after` = **审核**：金额已经是个正经数字了，现在判断它是否超过单笔限额。
>
> 一个实际的产品判断：**能在 `before` 里帮用户自动修正的，就不要让用户重填**。用户粘贴带空格的优惠码被拒绝，是很糟糕的体验；系统自动去掉空格，是好体验。这个决策该由 PM 做，写在 PRD 的「输入容错」一节。

### 5.3 Annotated 形式的校验器：规则可复用

**它解决什么问题**：同一条规则要用在很多字段/很多模型上，不想复制粘贴装饰器。

```python
from pydantic import AfterValidator
from typing import Annotated


def must_be_even(v: int) -> int:
    if v % 2:
        raise ValueError(f"{v} 不是偶数")
    return v


class Pack(BaseModel):
    qty: Annotated[int, AfterValidator(must_be_even)]


print(Pack(qty=4))
try:
    Pack(qty=5)
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
qty=4
Value error, 5 不是偶数
```

这种写法的好处：校验规则**就写在字段旁边**，一眼看得出这个字段有什么规则；而且 `Annotated[int, AfterValidator(must_be_even)]` 可以起个名字复用。

对应的还有 `BeforeValidator`、`PlainValidator`、`WrapValidator`。

> 👉 **PM 视角**：这是「**规则库**」的思路。把「必须是偶数」「必须是工作日」「必须是有效的省份编码」做成一个个可复用的规则组件，然后在字段上"挂载"。这跟你在低代码平台上给表单字段挂校验规则是同一件事。团队维护一个共享规则库，比每个人各写各的更可控。

### 5.4 一个校验器管多个字段

```python
class Names(BaseModel):
    first: str
    last: str

    @field_validator("first", "last")     # 列多个字段名
    @classmethod
    def no_space(cls, v: str) -> str:
        return v.strip()


print(Names(first="  A ", last=" B  "))
```

```text
first='A' last='B'
```

也可以用 `@field_validator("*")` 匹配所有字段。

### 5.5 model_validator：跨字段规则

**它解决什么问题**：规则涉及两个以上字段，单个字段的校验器看不到别人的值。

```python
from datetime import date
from pydantic import model_validator


class Campaign(BaseModel):
    start: date
    end: date
    budget: float = Field(gt=0)
    spent: float = Field(ge=0, default=0)

    @model_validator(mode="after")
    def check(self):
        if self.end <= self.start:
            raise ValueError("结束时间必须晚于开始时间")
        if self.spent > self.budget:
            raise ValueError(f"已花费 {self.spent} 超过预算 {self.budget}")
        return self          # 注意：返回 self，不是 cls


print(Campaign(start="2024-01-01", end="2024-02-01", budget=10000, spent=500))
try:
    Campaign(start="2024-03-01", end="2024-02-01", budget=100, spent=500)
except ValidationError as e:
    print(e)
```

```text
start=datetime.date(2024, 1, 1) end=datetime.date(2024, 2, 1) budget=10000.0 spent=500.0
1 validation error for Campaign
  Value error, 结束时间必须晚于开始时间 [type=value_error, input_value={'start': '2024-03-01', '...get': 100, 'spent': 500}, input_type=dict]
```

注意 `mode="after"` 的 model_validator：
- **不需要 `@classmethod`**（它拿到的是实例 `self`）；
- 必须 `return self`；
- 只报了第一个错误——因为一旦抛异常就中断了，不像字段级校验会全跑完。

> ⚠️ **坑**：错误信息里没有具体字段名（`loc` 是空的），因为这是"整个模型"的错误。如果你想让前端知道该在哪个输入框飘红，需要在业务层自己指定，或者把这条规则改写成挂在某个具体字段上的 `field_validator`（那样 `loc` 就是那个字段）。注意 `PydanticCustomError` 只能定制错误码（`type`）和文案（`msg`），**改不了 `loc`**。

> 👉 **PM 视角**：跨字段校验就是 PRD 里的「**联合校验规则**」，而且往往是最容易被漏掉的一类。清单：
> - 时间区间：结束 > 开始
> - 金额勾稽：已用 ≤ 总额、实付 = 原价 − 优惠
> - 逻辑互斥：选了"匿名"就不能填"署名"
> - 条件必填：类型为"企业"时，营业执照必填
>
> 这些规则在 PRD 里通常散落在各处，建议**单开一节「跨字段规则」集中写**，工程师就知道要写 `model_validator`。

### 5.6 「先算再判」：最有业务价值的模式

**它解决什么问题**：判断的依据不是用户填的任何一个字段，而是**由几个字段算出来的结果**。

```python
class Order(BaseModel):
    unit_price: float = Field(gt=0)
    qty: int = Field(gt=0)
    discount: float = Field(ge=0, le=1, default=0)
    total: float = 0                      # 用户不用填，我们算

    @model_validator(mode="after")
    def calc_total(self):
        # 第一步：算
        self.total = round(self.unit_price * self.qty * (1 - self.discount), 2)
        # 第二步：判
        if self.total > 50000:
            raise ValueError(f"单笔订单金额 {self.total} 超过 50000，需要走审批流")
        return self


print(Order(unit_price=99.9, qty=3, discount=0.1))
try:
    Order(unit_price=9999, qty=10)
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
unit_price=99.9 qty=3 discount=0.1 total=269.73
Value error, 单笔订单金额 99990.0 超过 50000，需要走审批流
```

> 👉 **PM 视角**：这是**审批流触发条件**的标准写法。你的 PRD 里几乎肯定有类似的句子：
>
> - 「订单金额超过 5 万元，需部门经理审批」
> - 「报销单据合计超过预算余额，禁止提交」
> - 「折扣后单价低于成本价，需总监特批」
>
> 这些规则的共同点是：**门槛判断的对象是一个计算结果，不是用户填的字段**。用户填的是单价、数量、折扣，系统算出总额，再拿总额去撞门槛。所以必须用 `model_validator(mode="after")`——只有到这一步，所有原始字段才都已经准备好了。
>
> 顺带一提：错误文案里带上了具体金额 `99990.0` 和门槛 `50000`。**好的错误提示要告诉用户"差多少"，而不只是"不行"**。这个细节在 PRD 里值得明确要求。

### 5.7 model_validator(mode="before")：改造原始结构

**它解决什么问题**：上游给的数据结构和我们想要的结构不一样，需要先"翻译"一下。

```python
from typing import Any


class Legacy(BaseModel):
    user_id: int
    user_name: str

    @model_validator(mode="before")
    @classmethod
    def flatten(cls, data: Any) -> Any:
        # 老系统传 {"user": {"id":..., "name":...}}，新系统传打平的
        if isinstance(data, dict) and "user" in data:
            u = data.pop("user")
            data["user_id"] = u["id"]
            data["user_name"] = u["name"]
        return data


print(Legacy.model_validate({"user": {"id": 7, "name": "老系统"}}))
print(Legacy.model_validate({"user_id": 8, "user_name": "新系统"}))
```

```text
user_id=7 user_name='老系统'
user_id=8 user_name='新系统'
```

> ⚠️ **坑**：`mode="before"` 的 model_validator 拿到的 `data` **不保证是 dict**——也可能是一个对象，或者任何东西。所以第一行几乎总要写 `if isinstance(data, dict)`。这也是官方建议「能用 after 就别用 before」的原因。

> 👉 **PM 视角**：这就是**接口适配层 / 防腐层**。当你要接一个老系统、一个第三方渠道，对方的字段结构你改不了，也不想让这套烂结构污染自己的业务代码——就在入口处做一次翻译。
>
> 产品上的对应决策是：**兼容逻辑要不要做，做多久**。上面这个例子同时兼容了两种格式，意味着老客户端可以不升级。什么时候删掉这段兼容代码，是个产品决策（取决于老版本用户占比），不是技术决策。

### 5.8 执行顺序：谁先谁后

```python
class Order2(BaseModel):
    a: int

    @model_validator(mode="before")
    @classmethod
    def m_before(cls, d): print("  1. model before"); return d

    @field_validator("a", mode="before")
    @classmethod
    def f_before(cls, v): print("  2. field before"); return v

    @field_validator("a", mode="after")
    @classmethod
    def f_after(cls, v): print("  3. field after"); return v

    @model_validator(mode="after")
    def m_after(self): print("  4. model after"); return self


Order2(a=1)
```

```text
  1. model before
  2. field before
  3. field after
  4. model after
```

完整流水线：

```text
原始输入
   │
   ├─▶ ① model_validator(before)   整体结构改造
   │
   ├─▶ ② field_validator(before)   单字段清洗
   │
   ├─▶    [Pydantic 类型转换 + Field 内置约束]
   │
   ├─▶ ③ field_validator(after)    单字段业务规则
   │
   └─▶ ④ model_validator(after)    跨字段规则 / 先算再判
          │
          ▼
      合法的模型对象
```

> 👉 **PM 视角**：这条流水线可以直接对应到**表单提交的审核链路**：整单预处理 → 逐项清洗 → 逐项格式校验 → 逐项业务校验 → 整单联合校验。你在 PRD 里描述校验规则时，按这个顺序组织，工程师几乎可以照着一比一实现。

### 5.9 再次强调：校验器默认不在赋值时跑

```python
c = Coupon(code="CP1")
c.code = "XX"          # 违反了"必须 CP 开头"，但不报错
print("默认赋值不校验:", c.code)
```

```text
默认赋值不校验: XX
```

```python
class Coupon2(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    code: str

    @field_validator("code")
    @classmethod
    def chk(cls, v: str) -> str:
        if not v.startswith("CP"):
            raise ValueError("必须 CP 开头")
        return v


c2 = Coupon2(code="CP1")
try:
    c2.code = "XX"
except ValidationError as e:
    print("开了 validate_assignment:", e.errors()[0]["msg"])
```

```text
开了 validate_assignment: Value error, 必须 CP 开头
```

---

## 6. 序列化：把对象再变回数据

校验是「进来」，序列化是「出去」。

### 6.0 序列化能力总表

| 方法/装饰器 | 作用 | 产出 |
|---|---|---|
| `model_dump()` | 转成 Python 字典 | `dict`（值还是 Python 对象） |
| `model_dump(mode="json")` | 转成"能直接变 JSON"的字典 | `dict`（值都是 JSON 原生类型） |
| `model_dump_json()` | 直接转成 JSON 字符串 | `str` |
| `include` / `exclude` | 挑字段 / 排除字段 | — |
| `exclude_none/unset/defaults` | 按条件排除 | — |
| `Field(exclude=True)` | 这个字段永不导出 | — |
| `@computed_field` | 增加一个「算出来的」导出字段 | — |
| `@field_serializer` | 定制某个字段的导出格式 | — |

### 6.1 model_dump vs model_dump_json

**它解决什么问题**：对象要交给下游（存库 / 返回给前端 / 发给第三方），得先变回普通数据。

```python
from decimal import Decimal
from datetime import datetime


class Item(BaseModel):
    name: str
    price: Decimal
    created: datetime


i = Item(name="鼠标", price="99.50", created="2024-05-01T12:00:00")
print("python 模式:", i.model_dump())
print("json   模式:", i.model_dump(mode="json"))
print("json 字符串:", i.model_dump_json())
print(i.model_dump_json(indent=2))
```

```text
python 模式: {'name': '鼠标', 'price': Decimal('99.50'), 'created': datetime.datetime(2024, 5, 1, 12, 0)}
json   模式: {'name': '鼠标', 'price': '99.50', 'created': '2024-05-01T12:00:00'}
json 字符串: {"name":"鼠标","price":"99.50","created":"2024-05-01T12:00:00"}
{
  "name": "鼠标",
  "price": "99.50",
  "created": "2024-05-01T12:00:00"
}
```

**关键区别**看 `created` 这一列：
- `model_dump()` 给的是 Python 的 `datetime` 对象——适合在 Python 内部继续处理；
- `model_dump(mode="json")` 给的是字符串 `"2024-05-01T12:00:00"`——适合直接扔给 `json.dumps` 或前端。

> ⚠️ **坑**：直接把 `model_dump()` 的结果丢给 `json.dumps()` 会报错，因为 `datetime` 和 `Decimal` 不是 JSON 原生类型。要么用 `mode="json"`，要么直接用 `model_dump_json()`。

> 👉 **PM 视角**：这两个方法对应产品里「**导出为内部格式**」和「**导出为交换格式**」的区别。就像 Excel 的「另存为 .xlsx」（保留完整格式和公式）和「另存为 .csv」（谁都能打开，但格式信息丢了）。
>
> 顺便注意 `Decimal("99.50")` 在 JSON 里变成了**字符串 `"99.50"`** 而不是数字。这是有意的——JSON 的数字类型没有精确小数，转成数字会丢精度。如果你的对接文档里写「金额字段为数字类型」，就会和这个默认行为冲突。**金额到底传字符串还是数字，是接口设计时必须明确的一条**，而且强烈建议传字符串。

### 6.2 挑字段：include / exclude 家族

**它解决什么问题**：同一个对象，给不同角色看不同的字段。

```python
class User(BaseModel):
    id: int
    name: str
    password: str
    email: str | None = None


u = User(id=1, name="tom", password="s3cret")
print(u.model_dump())
print(u.model_dump(exclude={"password"}))
print(u.model_dump(include={"id", "name"}))
print(u.model_dump(exclude_none=True))
print(u.model_dump(exclude_defaults=True))
print(u.model_dump(exclude_unset=True))
```

```text
{'id': 1, 'name': 'tom', 'password': 's3cret', 'email': None}
{'id': 1, 'name': 'tom', 'email': None}
{'id': 1, 'name': 'tom'}
{'id': 1, 'name': 'tom', 'password': 's3cret'}
{'id': 1, 'name': 'tom', 'password': 's3cret'}
{'id': 1, 'name': 'tom', 'password': 's3cret'}
```

| 参数 | 含义 |
|---|---|
| `include={...}` | 只要这几个字段（白名单） |
| `exclude={...}` | 除了这几个字段（黑名单） |
| `exclude_none=True` | 值为 None 的不导出 |
| `exclude_unset=True` | 用户没显式传的不导出 |
| `exclude_defaults=True` | 值等于默认值的不导出 |

如果某个字段**永远不该导出**，直接写在字段定义上：

```python
class User2(BaseModel):
    id: int
    password: str = Field(exclude=True)


print(User2(id=1, password="x").model_dump())
```

```text
{'id': 1}
```

> 👉 **PM 视角**：这一组参数直接对应两个高频产品需求：
>
> **1. 字段级权限 / 数据脱敏**。同一个用户对象，普通用户看到昵称头像，客服看到手机号，只有风控能看到身份证。`include`/`exclude` 就是这套「字段可见性矩阵」的实现方式。`Field(exclude=True)` 则是"任何人任何场景都不给看"——密码、密钥属于这一类，写在字段定义上比每次调用都记得排除要安全得多。
>
> **2. PATCH 语义**。`exclude_unset=True` 让你只导出用户真正改过的字段。这正是"局部更新"接口该有的行为：用户只改了昵称，就只发昵称，不要把整个对象发过去覆盖（否则会把别的端刚改的字段冲掉）。**"编辑资料"页面到底该整体覆盖还是局部更新，是个产品决策**，而 `exclude_unset` 是局部更新那一侧的实现。

### 6.3 computed_field：Excel 的公式列

**它解决什么问题**：有些字段不该让用户填，应该由系统根据别的字段算出来，但又需要出现在导出结果里。

```python
from pydantic import computed_field


class Cart(BaseModel):
    unit_price: float
    qty: int

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(self.unit_price * self.qty, 2)

    @computed_field(description="是否满足包邮门槛")
    @property
    def free_shipping(self) -> bool:
        return self.subtotal >= 99


c = Cart(unit_price=33.3, qty=3)
print(c.model_dump())
print(c.model_dump_json())
print("字段列表:", list(Cart.model_fields), "| 计算字段:", list(Cart.model_computed_fields))
```

```text
{'unit_price': 33.3, 'qty': 3, 'subtotal': 99.9, 'free_shipping': True}
{"unit_price":33.3,"qty":3,"subtotal":99.9,"free_shipping":true}
字段列表: ['unit_price', 'qty'] | 计算字段: ['subtotal', 'free_shipping']
```

注意三点：
1. 用户**不用也不能填** `subtotal`，它不在 `model_fields` 里；
2. 但它**会出现在导出结果里**，前端能直接拿到；
3. 计算字段可以引用另一个计算字段（`free_shipping` 用了 `subtotal`）。

**`computed_field` 和 5.6 节「先算再判」的区别**：

| | `computed_field` | `model_validator` 里赋值 |
|---|---|---|
| 字段是否要声明 | 不用声明 | 要声明（`total: float = 0`） |
| 何时计算 | 每次访问时现算 | 创建时算一次并存下来 |
| 能否参与校验 | ❌ 算出来就直接用了 | ✅ 可以拿来判断、抛错 |
| 适合 | 纯展示的派生值 | 要拿来做判断的中间值 |

> 👉 **PM 视角**：`computed_field` **就是 Excel 里的公式列**，一模一样的概念。小计 = 单价 × 数量、是否包邮 = 小计 ≥ 99、会员等级 = 按积分区间映射、账号年龄 = 今天 − 注册日。
>
> 在 PRD 里区分「**用户填的字段**」和「**系统算的字段**」是一个非常有价值的习惯，因为它同时决定了三件事：表单上显不显示这个输入框、接口文档里它是不是入参、以及数据库里要不要存这一列。把它们混在一张表里写，工程师就得靠猜。
>
> 建议 PRD 的字段表加一列「来源」，取值：用户填 / 系统算 / 上游传。

### 6.4 field_serializer：定制导出格式

**它解决什么问题**：内部存的格式和对外展示的格式不一样。

```python
from pydantic import field_serializer
from datetime import date


class Report(BaseModel):
    day: date
    amount: Decimal

    @field_serializer("day")
    def ser_day(self, v: date) -> str:
        return v.strftime("%Y年%m月%d日")

    @field_serializer("amount")
    def ser_amount(self, v: Decimal) -> str:
        return f"¥{v:,.2f}"


print(Report(day="2024-06-01", amount="12345.6").model_dump())
```

```text
{'day': '2024年06月01日', 'amount': '¥12,345.60'}
```

> ⚠️ **坑**：把「展示格式化」放进序列化器要谨慎。一旦这么做，这份数据就**不能再被同一个模型读回来了**（`"2024年06月01日"` 不是合法的日期输入）。展示格式化通常更适合放在前端。适合放在这里的是那种「对外协议规定的格式」，比如某个第三方要求日期必须是 `YYYYMMDD`。

> 👉 **PM 视角**：这对应「**同一份数据，不同的呈现口径**」。财务报表要 `¥12,345.60`，数据分析要 `12345.6`，第三方接口要 `1234560`（以分为单位）。谁来做这个转换，是一个架构决策：放后端（统一、但不灵活）还是放前端（灵活、但每个端要各做一遍且容易不一致）。**多端产品建议放后端**，单一 Web 产品放前端更灵活。

### 6.5 经典大坑：按「声明的类型」序列化

**它解决什么问题**：这是 Pydantic 最容易让人踩坑的一个行为，必须知道。

```python
class Base(BaseModel):
    base_field: int


class Sub(Base):                 # 继承，多一个字段
    sub_field: str


class Main(BaseModel):
    model: Base                  # 声明为 Base


m = Main(model=Sub(base_field=1, sub_field="会不见"))
print("m.model 实际是:", type(m.model).__name__)
print("dump 结果      :", m.model_dump())
```

```text
m.model 实际是: Sub
dump 结果      : {'model': {'base_field': 1}}
```

**`sub_field` 消失了。** 数据没丢（`m.model` 确实是个 `Sub` 对象），但导出时按 `Base` 的定义只导出了 `base_field`。

原因：Pydantic **按你声明的类型序列化，不按运行时的实际类型**。你说这一列是 `Base`，它就只导出 `Base` 有的字段。

**修法 1（推荐）：用判别联合**（第 8 章详讲）

```python
class SubA(BaseModel):
    type: Literal["a"] = "a"
    base_field: int
    sub_field: str


class MainOK(BaseModel):
    model: SubA


print(MainOK(model=SubA(base_field=1, sub_field="在的")).model_dump())
```

```text
{'model': {'type': 'a', 'base_field': 1, 'sub_field': '在的'}}
```

**修法 2（应急）：`serialize_as_any=True`**

```python
print(m.model_dump(serialize_as_any=True))
```

```text
{'model': {'base_field': 1, 'sub_field': '会不见'}}
```

> ⚠️ **坑**：这是一个**静默失败**——不报错、不警告，字段就是没了。线上表现是「某些订单的某些字段前端拿不到」，排查起来很痛苦。凡是模型里用了继承 + 父类型声明，都要检查这一点。

> 👉 **PM 视角**：翻译成产品语言：**「你的表单模板声明了这一栏填『通用附件』，那么就算用户实际上传的是『企业营业执照』，归档时也只会记录『通用附件』那几项通用信息，营业执照特有的信息会被丢掉。」**
>
> 这个坑对应的产品场景非常典型：一个通用的「消息」对象，下面有「短信/邮件/推送」三种子类型，各自有独特字段。如果建模时用「继承」表达这个关系，就会掉进这个坑。**正确的建模方式是"带类型标记的联合"（第 8 章）**——这也恰好是你在 PRD 里画表单联动时最自然的想法：先选类型，再显示对应字段。

### 6.6 未知字段默认被悄悄丢弃

```python
class Strict(BaseModel):
    a: int


print(Strict.model_validate({"a": 1, "b": 2}).model_dump())
```

```text
{'a': 1}
```

多传的 `b` 被静默忽略了。想报错要开 `extra="forbid"`（见 10.1）。

> 👉 **PM 视角**：默认的"忽略"是宽容的，好处是上游加字段不会打挂你；坏处是**上游把字段名拼错了，你也不会发现**——`phoneNumber` 拼成 `phonNumber`，数据就悄悄没了。对内部接口建议开 `extra="forbid"`（严格对齐），对外部/第三方接口建议保持默认（容错）。

---

## 7. JSON Schema：把你画的表变成一份说明书 ★

**这是全书承上启下的一章，请慢慢看。**

前面所有章节都在讲「怎么定义一张表」。这一章讲的是：**这张表可以被自动翻译成一份机器能读懂的说明书**。

而这份说明书，正是后面 Pydantic AI 让大模型「按格式输出」的底层机制。

### 7.1 核心概念：表 → 说明书

**它解决什么问题**：把「代码里的字段规则」变成「任何系统都能读懂的标准格式描述」。

```text
   ┌──────────────────────────┐                    ┌────────────────────────────┐
   │   你写的 Pydantic 模型     │                    │      JSON Schema           │
   │   （表 / 数据契约）        │  ──────────────▶   │      （说明书）             │
   │                          │  model_json_schema │                            │
   │  class User(BaseModel):  │                    │  {                         │
   │      name: str           │                    │    "type": "object",       │
   │      age: int            │                    │    "properties": {...},    │
   │                          │                    │    "required": [...]       │
   └──────────────────────────┘                    │  }                         │
                                                   └────────────┬───────────────┘
                                                                │
                          ┌─────────────────────────────────────┼──────────────────────────┐
                          ▼                                     ▼                          ▼
                ┌──────────────────┐              ┌──────────────────────┐    ┌──────────────────────┐
                │  API 文档         │              │  前端表单自动生成      │    │  大模型结构化输出 ★   │
                │  (OpenAPI/Swagger)│              │  (低代码 / 表单引擎)  │    │  (Pydantic AI)       │
                └──────────────────┘              └──────────────────────┘    └──────────────────────┘
```

最小例子：

```python
import json
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int


print(json.dumps(User.model_json_schema(), indent=2, ensure_ascii=False))
```

```json
{
  "properties": {
    "name": {
      "title": "Name",
      "type": "string"
    },
    "age": {
      "title": "Age",
      "type": "integer"
    }
  },
  "required": [
    "name",
    "age"
  ],
  "title": "User",
  "type": "object"
}
```

逐块解读这份说明书：

| Schema 里的键 | 含义 | 对应 PRD 里的什么 |
|---|---|---|
| `"type": "object"` | 这是一张表（不是单个值） | 「表单」/「对象」 |
| `"title": "User"` | 这张表叫什么 | 表名 |
| `"properties"` | 有哪些列 | 字段清单 |
| `"required"` | 哪些列必填 | 必填标记那一列 |
| 每个字段的 `"type"` | 这一列填什么类型 | 「类型」那一列 |
| 每个字段的 `"title"` | 这一列的显示名（自动从字段名生成） | 字段中文名 |

注意 `title` 是 Pydantic **自动**从字段名生成的：`user_name` → `"User Name"`。

> 👉 **PM 视角**：这一步是本书最重要的观念转换。
>
> **你在 PRD 里画的那张字段规则表，工程师用 Pydantic 写一遍之后，就能"免费"得到一份标准化、机器可读的说明书。** 而这份说明书可以直接喂给：Swagger 生成接口文档、前端表单引擎自动渲染表单、以及——大模型。
>
> 这意味着「PRD 的字段表」不再是一份写完就过期的 Word 文档，而是**唯一事实来源（single source of truth）**：改代码里的模型，文档、表单、AI 提示词自动跟着变。这是你可以在团队里推动的一个非常实际的改进。

### 7.2 description 如何进入 schema

**它解决什么问题**：让「字段的业务含义」也进入说明书，而不只是类型。

```python
from typing import Literal
from pydantic import Field, ConfigDict


class Feedback(BaseModel):
    """用户反馈工单。"""
    model_config = ConfigDict(title="用户反馈")

    title: str = Field(description="一句话概括反馈内容", max_length=50)
    sentiment: Literal["正面", "中性", "负面"] = Field(description="整体情绪倾向")
    score: int = Field(ge=1, le=5, description="满意度打分，1 最差 5 最好")
    tags: list[str] = Field(default_factory=list, description="问题标签，最多 3 个", max_length=3)
    need_followup: bool = Field(default=False, description="是否需要人工跟进")


print(json.dumps(Feedback.model_json_schema(), indent=2, ensure_ascii=False))
```

```json
{
  "description": "用户反馈工单。",
  "properties": {
    "title": {
      "description": "一句话概括反馈内容",
      "maxLength": 50,
      "title": "Title",
      "type": "string"
    },
    "sentiment": {
      "description": "整体情绪倾向",
      "enum": [
        "正面",
        "中性",
        "负面"
      ],
      "title": "Sentiment",
      "type": "string"
    },
    "score": {
      "description": "满意度打分，1 最差 5 最好",
      "maximum": 5,
      "minimum": 1,
      "title": "Score",
      "type": "integer"
    },
    "tags": {
      "description": "问题标签，最多 3 个",
      "items": {
        "type": "string"
      },
      "maxItems": 3,
      "title": "Tags",
      "type": "array"
    },
    "need_followup": {
      "default": false,
      "description": "是否需要人工跟进",
      "title": "Need Followup",
      "type": "boolean"
    }
  },
  "required": [
    "title",
    "sentiment",
    "score"
  ],
  "title": "用户反馈",
  "type": "object"
}
```

**三条信息来源**：

| Schema 里的位置 | 来自哪里 |
|---|---|
| 顶层 `"description"` | 类的**文档字符串**（`"""用户反馈工单。"""`） |
| 顶层 `"title"` | `model_config = ConfigDict(title="用户反馈")`，不设就用类名 |
| 字段的 `"description"` | `Field(description=...)` |

**`required` 是怎么算出来的**：`title`/`sentiment`/`score` 没有默认值 → 必填；`tags` 有 `default_factory`、`need_followup` 有 `default=False` → 不必填，且默认值 `false` 也写进了 schema。

> 👉 **PM 视角**：**这段输出请多看两眼——因为这就是大模型将会"看见"的东西。**
>
> 模型看到 `"description": "满意度打分，1 最差 5 最好"` 和 `"minimum": 1, "maximum": 5`，就知道该填 1–5 的整数，而且知道 1 是差评。如果你的 description 写成「打分」两个字，模型就不知道是 5 分制还是 100 分制，也不知道分高是好是坏。
>
> 换句话说：**`description` 是 PM 写的提示词，只不过它长在字段旁边。** 这是产品经理在 AI 项目里最有杠杆、也最容易被忽视的一个发力点。

### 7.3 约束如何在 schema 里表达

**它解决什么问题**：搞清楚 Python 里的约束和 JSON Schema 标准词汇的对应关系（名字不一样）。

| Pydantic 写法 | JSON Schema 里变成 | 说明 |
|---|---|---|
| `Field(gt=0)` | `"exclusiveMinimum": 0` | 严格大于 |
| `Field(ge=1)` | `"minimum": 1` | 大于等于 |
| `Field(lt=100)` | `"exclusiveMaximum": 100` | 严格小于 |
| `Field(le=5)` | `"maximum": 5` | 小于等于 |
| `Field(min_length=6)`（字符串） | `"minLength": 6` | |
| `Field(max_length=50)`（字符串） | `"maxLength": 50` | |
| `Field(min_length=1)`（列表） | `"minItems": 1` | 同一个参数，列表上变成 items |
| `Field(max_length=20)`（列表） | `"maxItems": 20` | |
| `Field(pattern=r"^1\d{10}$")` | `"pattern": "^1\\d{10}$"` | 正则原样带过去 |
| `Literal["A","B"]` | `"enum": ["A","B"]` | 选项清单 |
| `str` | `"type": "string"` | |
| `int` | `"type": "integer"` | |
| `float` | `"type": "number"` | |
| `bool` | `"type": "boolean"` | |
| `list[X]` | `"type": "array", "items": {...}` | |
| `dict[str,X]` | `"type": "object"` | |
| `X \| None` | `"anyOf": [{...}, {"type":"null"}]` | 可空表示为「或者是 null」 |
| `date` | `"type": "string", "format": "date"` | |
| `datetime` | `"type": "string", "format": "date-time"` | |
| `ConfigDict(extra="forbid")` | `"additionalProperties": false` | 不许多填 |
| `@computed_field` | `"readOnly": true` | 只读列。**仅 `mode="serialization"` 下出现**；默认的 validation 模式里计算字段根本不进 schema |

可空字段的样子（来自 7.9 的实跑输出）：

```json
"remark": {
  "anyOf": [
    { "maxLength": 200, "type": "string" },
    { "type": "null" }
  ],
  "default": null,
  "title": "Remark"
}
```

> 👉 **PM 视角**：这张对照表的价值在于——**当你看到工程师给你的接口文档（Swagger）里写着 `exclusiveMinimum: 0`，你要能立刻反应过来"这是价格必须大于 0，0 元不行"**。反过来，当你在 PRD 里写「价格 > 0」，你也知道它最终会变成这一行。这是产品和研发之间少数几个可以做到"字面对齐"的地方。
>
> 特别注意 `gt` → `exclusiveMinimum` 这个改名。`minimum` 和 `exclusiveMinimum` 差一个字，业务含义差一个边界值，而边界值问题是测试用例里最常出 bug 的地方。

### 7.4 嵌套模型：$defs 和 $ref 是什么

**它解决什么问题**：一张表里引用了另一张表，说明书要怎么写才不重复。

```python
class Address(BaseModel):
    city: str
    zipcode: str = Field(pattern=r"^\d{6}$")


class Person(BaseModel):
    name: str
    home: Address
    others: list[Address] = []


print(json.dumps(Person.model_json_schema(), indent=2, ensure_ascii=False))
```

```json
{
  "$defs": {
    "Address": {
      "properties": {
        "city": {
          "title": "City",
          "type": "string"
        },
        "zipcode": {
          "pattern": "^\\d{6}$",
          "title": "Zipcode",
          "type": "string"
        }
      },
      "required": [
        "city",
        "zipcode"
      ],
      "title": "Address",
      "type": "object"
    }
  },
  "properties": {
    "name": {
      "title": "Name",
      "type": "string"
    },
    "home": {
      "$ref": "#/$defs/Address"
    },
    "others": {
      "default": [],
      "items": {
        "$ref": "#/$defs/Address"
      },
      "title": "Others",
      "type": "array"
    }
  },
  "required": [
    "name",
    "home"
  ],
  "title": "Person",
  "type": "object"
}
```

**`$defs` 和 `$ref` 是一对**：

```text
  ┌────────────────────────────────────────────────┐
  │  "$defs": {          ← 「附录：子表定义区」      │
  │      "Address": { ...完整的 Address 表定义... } │
  │  }                                             │
  │                                                │
  │  "properties": {                               │
  │      "home":   { "$ref": "#/$defs/Address" }   │  ← 「详见附录 Address」
  │      "others": { "type": "array",              │
  │                  "items": {                    │
  │                     "$ref": "#/$defs/Address"  │  ← 「每一项详见附录 Address」
  │                  } }                           │
  │  }                                             │
  └────────────────────────────────────────────────┘
```

- **`$defs`** = 说明书末尾的「**附录 / 子表定义区**」，每个被引用的子模型在这里完整定义一次；
- **`$ref`** = 正文里的「**详见附录 X**」，`#/$defs/Address` 读作「本文档 → $defs 节 → Address 条目」。

**为什么要这么绕？** 因为 `Address` 被引用了两次（`home` 和 `others` 里各一次）。如果不用引用，同样的定义要抄两遍；表结构一深，说明书会爆炸式膨胀。而且自引用的树形结构（4.6 节的 `Category`）**根本没法展开**——它是无限层的，只能靠引用来表达。

> 👉 **PM 视角**：`$defs` + `$ref` 就是你写长篇 PRD 时用的那个技巧——**把重复出现的定义抽到附录，正文里写"字段定义见附录 3.2"**。「收货地址」这个结构在下单页、地址簿、售后单里都出现，你不会在 PRD 里抄三遍，你会写一次然后各处引用。JSON Schema 的做法一模一样。
>
> 实用提醒：**有些大模型的结构化输出接口对 `$ref` 的支持有限**（尤其是嵌套很深或有循环引用时）。所以在设计给 AI 用的输出结构时，**层级不要太深**（一般不超过 2–3 层），这是个需要 PM 参与权衡的设计约束——结构越精细，模型填错的概率越高，接口报错的概率也越高。

### 7.5 两种模式：validation 和 serialization

**它解决什么问题**：「进来时」的说明书和「出去时」的说明书内容不一样——计算字段只在出去时存在。

```python
from pydantic import computed_field


class C(BaseModel):
    a: int

    @computed_field
    @property
    def double(self) -> int:
        return self.a * 2


print("validation:", list(C.model_json_schema(mode="validation")["properties"]))
print("serialization:", list(C.model_json_schema(mode="serialization")["properties"]))
```

```text
validation: ['a']
serialization: ['a', 'double']
```

| 模式 | 描述的是 | 用在哪 |
|---|---|---|
| `mode="validation"`（默认） | **接口的入参**长什么样 | 给前端做表单、给大模型填表 ★ |
| `mode="serialization"` | **接口的返回**长什么样 | API 响应文档 |

> 👉 **PM 视角**：这正好对应接口文档里的「**请求参数**」和「**响应字段**」两张表。计算字段（小计、是否包邮）只出现在响应里，不出现在请求里——因为用户不该填它。
>
> 让大模型填表时用的是 **validation 模式**，所以模型永远不会被要求去填一个计算字段。这个设计很聪明：你想让模型算的东西，就定义成普通字段；不想让模型算、要自己算的，就定义成 `computed_field`。**这是一个可以由 PM 来做的关键决策**：哪些数字交给 AI 判断，哪些数字必须由系统精确计算。（涉及钱的，永远选后者。）

### 7.6 alias 对说明书的影响

```python
class Al(BaseModel):
    user_name: str = Field(alias="userName")


print("by_alias=True (默认):", list(Al.model_json_schema()["properties"]))
print("by_alias=False      :", list(Al.model_json_schema(by_alias=False)["properties"]))
```

```text
by_alias=True (默认): ['userName']
by_alias=False      : ['user_name']
```

默认生成的说明书用的是**对外的名字**（alias）——这是对的，因为说明书是给外部看的。

### 7.7 json_schema_extra：往说明书里塞自定义内容

```python
class P(BaseModel):
    sku: str = Field(description="商品编码", examples=["SKU-001", "SKU-002"],
                     json_schema_extra={"x-internal": True})
```

```json
{
  "sku": {
    "description": "商品编码",
    "examples": ["SKU-001", "SKU-002"],
    "title": "Sku",
    "type": "string",
    "x-internal": true
  }
}
```

> 👉 **PM 视角**：`x-` 开头的自定义键是 OpenAPI 的惯例，用来放「标准之外的、我们自己约定的信息」。比如 `x-pii: true` 标记这是个人敏感信息、`x-since: "v2.3"` 标记这个字段从哪个版本开始有。**这可以成为一套很实用的数据治理机制**——在字段上打标，然后写个脚本扫描所有模型，自动生成「全系统的个人信息字段清单」交给法务。合规检查从"人肉翻代码"变成"跑个脚本"。

### 7.8 ★ 这就是大模型「按格式输出」的底层机制

**它解决什么问题**：让大模型不要自由发挥，而是老老实实按你定的表格填。

完整流程：

```text
 ①  PM 定义需求：「从用户反馈里提取：一句话摘要、情绪、打分、标签、是否需跟进」
                                  │
                                  ▼
 ②  工程师写成 Pydantic 模型（就是 7.2 的 Feedback 类）
                                  │
                                  ▼
 ③  Feedback.model_json_schema()  →  一份 949 字符的说明书
                                  │
                                  ▼
 ④  说明书 + 用户原始反馈文本  →  一起发给大模型
                                  │
                                  ▼
 ⑤  模型返回一段 JSON 文本
                                  │
                                  ▼
 ⑥  Feedback.model_validate_json(模型输出)
                                  │
                     ┌────────────┴────────────┐
                     ▼                         ▼
              校验通过 → 拿到对象         校验失败 → ValidationError
              直接 fb.score               把错误信息发回给模型，让它重填
```

实跑一遍第 ③⑤⑥ 步：

```python
schema = Feedback.model_json_schema()
print("发给模型的 schema 大小:", len(json.dumps(schema)), "字符")

# 模拟大模型返回的 JSON
fake_llm_output = '{"title":"App 启动很慢","sentiment":"负面","score":2,"tags":["性能"],"need_followup":true}'

fb = Feedback.model_validate_json(fake_llm_output)
print("解析回对象:", fb)
print("直接拿字段:", fb.score, fb.sentiment)
```

```text
发给模型的 schema 大小: 949 字符
解析回对象: title='App 启动很慢' sentiment='负面' score=2 tags=['性能'] need_followup=True
直接拿字段: 2 负面
```

**模型输出不合规时会怎样**：

```python
bad = '{"title":"App 启动很慢","sentiment":"很生气","score":8,"tags":["a","b","c","d"]}'
try:
    Feedback.model_validate_json(bad)
except ValidationError as e:
    print(e)
```

```text
3 validation errors for 用户反馈
sentiment
  Input should be '正面', '中性' or '负面' [type=literal_error, input_value='很生气', input_type=str]
score
  Input should be less than or equal to 5 [type=less_than_equal, input_value=8, input_type=int]
tags
  List should have at most 3 items after validation, not 4 [type=too_long, input_value=['a', 'b', 'c', 'd'], input_type=list]
```

模型自己发挥了三处：情绪写成了不在选项里的「很生气」、打分给了 5 分制之外的 8、标签给了 4 个超过上限。**这三处全部被拦住了，而且报错信息本身就是一份可以直接发回给模型的"修改意见"。**

> 👉 **PM 视角**：**这一节是整本书的枢纽，请务必理解到位。**
>
> 大模型天生是"自由发挥"的——你让它总结反馈，它可能返回一段散文、可能返回 JSON、可能返回 Markdown 表格，每次都不一样。这在 Demo 里没问题，在产品里是灾难：下游代码根本没法处理。
>
> Pydantic 提供的是**结构化输出的两道保险**：
> 1. **事前**：把 schema 发给模型，明确告诉它「必须按这张表填，情绪只能三选一，分数 1–5」——大幅提高一次填对的概率；
> 2. **事后**：用同一个模型校验它的输出——填错了当场发现，不会让脏数据流进业务。
>
> 而且第 2 步的报错还能自动喂回给模型让它重试。这就是"AI 应用能不能上生产"的关键分水岭：**有 schema 约束的 AI 输出是可控的组件，没有约束的 AI 输出是不可控的随机事件。**
>
> 对 PM 的直接启示：当你在设计一个 AI 功能时，**你的核心工作其实是设计那张表**——要提取哪些字段、每个字段的取值范围、每个字段的说明怎么写。这活儿跟你设计一张后台表单没有本质区别，是产品经理的主场，不是算法工程师的主场。

### 7.9 端到端示例：一份 PRD 变成一份说明书

把前面所有知识点串起来。假设 PRD 是这样的：

> **下单接口**
> - 买家 ID：整数，必填，必须大于 0
> - 商品明细：列表，必填，1–20 条；每条包含 商品编码（SKU-开头+4位数字）、单价（>0）、数量（1–99）
> - 优惠券：选填；包含 券码、折扣率（0–1）
> - 备注：选填，最多 200 字
> - 系统计算：订单原价、应付金额
> - 业务规则：订单原价不足 100 元不可使用优惠券
> - 不允许传未定义的字段

代码：

```python
class Sku(BaseModel):
    sku_id: str = Field(pattern=r"^SKU-\d{4}$", description="商品编码")
    price: float = Field(gt=0, description="单价，单位元")
    qty: int = Field(gt=0, le=99, description="购买数量")


class Coupon(BaseModel):
    code: str
    off: float = Field(ge=0, le=1, description="折扣率，0.1 表示打 9 折")


class OrderReq(BaseModel):
    model_config = ConfigDict(extra="forbid", title="下单请求")

    buyer_id: int = Field(gt=0)
    items: list[Sku] = Field(min_length=1, max_length=20, description="购物车明细")
    coupon: Coupon | None = None
    remark: str | None = Field(default=None, max_length=200)

    @computed_field(description="订单原价")
    @property
    def gross(self) -> float:
        return round(sum(i.price * i.qty for i in self.items), 2)

    @computed_field(description="应付金额")
    @property
    def payable(self) -> float:
        off = self.coupon.off if self.coupon else 0
        return round(self.gross * (1 - off), 2)

    @model_validator(mode="after")
    def check(self):
        if self.coupon and self.gross < 100:
            raise ValueError("订单原价不足 100 元，不可使用优惠券")
        return self
```

正常输入：

```python
payload = {
    "buyer_id": 1001,
    "items": [{"sku_id": "SKU-0001", "price": 59.9, "qty": 2},
              {"sku_id": "SKU-0002", "price": 12.5, "qty": 1}],
    "coupon": {"code": "CP10", "off": 0.1},
}
print(OrderReq.model_validate(payload).model_dump_json(indent=2))
```

```json
{
  "buyer_id": 1001,
  "items": [
    {"sku_id": "SKU-0001", "price": 59.9, "qty": 2},
    {"sku_id": "SKU-0002", "price": 12.5, "qty": 1}
  ],
  "coupon": {"code": "CP10", "off": 0.1},
  "remark": null,
  "gross": 132.3,
  "payable": 119.07
}
```

违规输入，四个错误一次报全：

```python
bad = {"buyer_id": 0, "items": [], "coupon": {"code": "X", "off": 2}, "unknown": 1}
try:
    OrderReq.model_validate(bad)
except ValidationError as e:
    print(e)
```

```text
4 validation errors for 下单请求
buyer_id
  Input should be greater than 0 [type=greater_than, input_value=0, input_type=int]
items
  List should have at least 1 item after validation, not 0 [type=too_short, input_value=[], input_type=list]
coupon.off
  Input should be less than or equal to 1 [type=less_than_equal, input_value=2, input_type=int]
unknown
  Extra inputs are not permitted [type=extra_forbidden, input_value=1, input_type=int]
```

它自动生成的说明书（`mode="serialization"`，即接口返回结构）：

```json
{
  "$defs": {
    "Coupon": {
      "properties": {
        "code": {"title": "Code", "type": "string"},
        "off": {
          "description": "折扣率，0.1 表示打 9 折",
          "maximum": 1, "minimum": 0,
          "title": "Off", "type": "number"
        }
      },
      "required": ["code", "off"],
      "title": "Coupon", "type": "object"
    },
    "Sku": {
      "properties": {
        "sku_id": {
          "description": "商品编码",
          "pattern": "^SKU-\\d{4}$",
          "title": "Sku Id", "type": "string"
        },
        "price": {
          "description": "单价，单位元",
          "exclusiveMinimum": 0,
          "title": "Price", "type": "number"
        },
        "qty": {
          "description": "购买数量",
          "exclusiveMinimum": 0, "maximum": 99,
          "title": "Qty", "type": "integer"
        }
      },
      "required": ["sku_id", "price", "qty"],
      "title": "Sku", "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "buyer_id": {"exclusiveMinimum": 0, "title": "Buyer Id", "type": "integer"},
    "items": {
      "description": "购物车明细",
      "items": {"$ref": "#/$defs/Sku"},
      "maxItems": 20, "minItems": 1,
      "title": "Items", "type": "array"
    },
    "coupon": {
      "anyOf": [{"$ref": "#/$defs/Coupon"}, {"type": "null"}],
      "default": null
    },
    "remark": {
      "anyOf": [{"maxLength": 200, "type": "string"}, {"type": "null"}],
      "default": null, "title": "Remark"
    },
    "gross": {
      "description": "订单原价", "readOnly": true,
      "title": "Gross", "type": "number"
    },
    "payable": {
      "description": "应付金额", "readOnly": true,
      "title": "Payable", "type": "number"
    }
  },
  "required": ["buyer_id", "items", "gross", "payable"],
  "title": "下单请求", "type": "object"
}
```

把 PRD 的每一条和 schema 的每一行对起来看：

| PRD 原话 | schema 里的表现 |
|---|---|
| 买家 ID 必须大于 0 | `"buyer_id": {"exclusiveMinimum": 0}` |
| 商品明细 1–20 条 | `"minItems": 1, "maxItems": 20` |
| SKU-开头+4位数字 | `"pattern": "^SKU-\\d{4}$"` |
| 数量 1–99 | `"exclusiveMinimum": 0, "maximum": 99` |
| 优惠券选填 | `"anyOf": [{...}, {"type":"null"}], "default": null` |
| 备注最多 200 字 | `"maxLength": 200` |
| 系统计算的字段 | `"readOnly": true` |
| 不允许未定义字段 | `"additionalProperties": false` |
| 原价不足 100 不可用券 | **不在 schema 里**（自定义业务规则表达不了） |

> ⚠️ **坑**：最后一行很重要。**`model_validator` 里的自定义业务规则不会出现在 JSON Schema 里**。JSON Schema 只能表达"结构性"约束（类型、范围、长度、枚举），表达不了"原价不足 100 不可用券"这种业务逻辑。
>
> 这对 AI 场景的含义是：**这类规则模型看不到，所以它可能生成违反业务规则的结果**。解决办法有两个：（1）把规则写进某个字段的 `description` 里让模型看到；（2）依赖事后校验 + 报错重试。生产环境两个都要做。

### 7.10 顶层与多模型 schema

**它解决什么问题**：一次性把多个模型的说明书合并成一份（做完整的 API 文档时用）。

```python
from pydantic.json_schema import models_json_schema


class A1(BaseModel):
    x: int


class B1(BaseModel):
    y: A1


keys, top = models_json_schema([(A1, "validation"), (B1, "validation")])
print(json.dumps(top, indent=2, ensure_ascii=False))
```

```json
{
  "$defs": {
    "A1": {
      "properties": {"x": {"title": "X", "type": "integer"}},
      "required": ["x"], "title": "A1", "type": "object"
    },
    "B1": {
      "properties": {"y": {"$ref": "#/$defs/A1"}},
      "required": ["y"], "title": "B1", "type": "object"
    }
  }
}
```

**定制引用路径**（对接 OpenAPI 时，引用前缀要求是 `#/components/schemas/`）：

```python
print(json.dumps(B1.model_json_schema(ref_template="#/components/schemas/{model}"),
                 indent=2, ensure_ascii=False))
```

```json
{
  "$defs": { "A1": {...} },
  "properties": {
    "y": { "$ref": "#/components/schemas/A1" }
  },
  "required": ["y"],
  "title": "B1",
  "type": "object"
}
```

> 👉 **PM 视角**：`ref_template` 这个参数解释了为什么 FastAPI 这类框架能自动生成完整的 Swagger 文档——它就是拿所有 Pydantic 模型的 schema，按 OpenAPI 规范拼成一份大文档。**你团队的接口文档能不能做到"永远和代码一致"，取决于是不是走的这条路**（自动生成）还是人肉维护 Word。这是值得推动的一件事。

---

## 8. 判别联合：「选了 A 才出现 B 组字段」

### 8.1 它解决什么问题

这是产品里再熟悉不过的一类需求——**表单联动 / 条件字段**：

- 发送通知：选「短信」要填手机号+模板 ID；选「邮件」要填收件地址+主题+抄送；选「App 推送」要填设备 token+角标数
- 支付方式：选「银行卡」要填卡号+户名；选「支付宝」要填账号
- 发票类型：选「增值税专用发票」要填税号+开户行；选「普通发票」只要抬头

共同结构是：**一个类型选择器 + 每种类型各自的一组字段**。

在 Pydantic 里，这叫 **discriminated union（判别联合）**，`type` 那个字段叫 **discriminator（判别器）**。

### 8.2 不用判别器会怎样

先看反面教材：

```python
class Sms(BaseModel):
    phone: str
    template_id: str


class Email(BaseModel):
    address: str
    subject: str


class NotifyBad(BaseModel):
    channel: Sms | Email          # 普通联合，没有判别器


try:
    NotifyBad(channel={"phone": "138", "subject": "x"})
except ValidationError as e:
    print(e)
```

```text
2 validation errors for NotifyBad
channel.Sms.template_id
  Field required [type=missing, input_value={'phone': '138', 'subject': 'x'}, input_type=dict]
channel.Email.address
  Field required [type=missing, input_value={'phone': '138', 'subject': 'x'}, input_type=dict]
```

Pydantic 挨个试了 `Sms` 和 `Email`，两个都失败，于是**把两组失败原因都报给你**。用户到底想发短信还是发邮件？程序不知道，报错也就没法给出有用的指引。数据量一多、分支一多，这种报错完全没法读。

### 8.3 加上判别器

```python
from typing import Annotated, Literal


class SmsCfg(BaseModel):
    type: Literal["sms"]                            # ← 判别器字段
    phone: str = Field(pattern=r"^1\d{10}$")
    template_id: str


class EmailCfg(BaseModel):
    type: Literal["email"]
    address: str
    subject: str
    cc: list[str] = []


class PushCfg(BaseModel):
    type: Literal["push"]
    device_token: str
    badge: int = Field(ge=0, default=1)


# 关键这一行：告诉 Pydantic 用 type 字段来分辨
Channel = Annotated[SmsCfg | EmailCfg | PushCfg, Field(discriminator="type")]


class Notification(BaseModel):
    title: str
    channel: Channel
```

用起来：

```python
n = Notification.model_validate({
    "title": "订单已发货",
    "channel": {"type": "sms", "phone": "13800138000", "template_id": "T001"},
})
print(n)
print(n.model_dump())

n2 = Notification.model_validate({
    "title": "周报",
    "channel": {"type": "email", "address": "a@b.com", "subject": "本周数据"},
})
print(n2.model_dump())
```

```text
title='订单已发货' channel=SmsCfg(type='sms', phone='13800138000', template_id='T001')
{'title': '订单已发货', 'channel': {'type': 'sms', 'phone': '13800138000', 'template_id': 'T001'}}
{'title': '周报', 'channel': {'type': 'email', 'address': 'a@b.com', 'subject': '本周数据', 'cc': []}}
```

结构图：

```text
                          channel
                             │
                   看 type 这一个字段
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   type="sms"           type="email"         type="push"
   ┌──────────┐        ┌──────────┐        ┌──────────────┐
   │ phone    │        │ address  │        │ device_token │
   │ template │        │ subject  │        │ badge        │
   │  _id     │        │ cc       │        │              │
   └──────────┘        └──────────┘        └──────────────┘
```

### 8.4 报错变得精准

**选了不存在的类型**：

```text
1 validation error for Notification
channel
  Input tag 'fax' found using 'type' does not match any of the expected tags: 'sms', 'email', 'push'
  [type=union_tag_invalid, input_value={'type': 'fax', 'no': '1'}, input_type=dict]
```

直接告诉你「可选的类型只有这三个」。

**类型对了，但该分支的字段缺了**：

```text
1 validation error for Notification
channel.sms.template_id
  Field required [type=missing, input_value={'type': 'sms', 'phone': '13800138000'}, input_type=dict]
```

`channel.sms.template_id` —— 精确到「channel 字段的 sms 分支的 template_id」。对比 8.2 节那个「两个分支的错误全报一遍」，天差地别。

**忘了传 type**：

```text
1 validation error for Notification
channel
  Unable to extract tag using discriminator 'type' [type=union_tag_not_found, input_value={'phone': '13800138000'}, input_type=dict]
```

| 错误码 | 含义 | 前端该怎么处理 |
|---|---|---|
| `union_tag_not_found` | 没传类型 | 提示「请先选择通知方式」 |
| `union_tag_invalid` | 类型不在选项里 | 提示「不支持的通知方式」 |
| 分支内的普通错误 | 类型对了但字段有问题 | 在对应分支的输入框上飘红 |

### 8.5 序列化不会丢字段

回顾 6.5 节那个「继承导致字段消失」的坑。判别联合没有这个问题：

```python
print(Notification(title="t", channel=PushCfg(type="push", device_token="abc")).model_dump())
```

```text
{'title': 't', 'channel': {'type': 'push', 'device_token': 'abc', 'badge': 1}}
```

`device_token` 和 `badge` 都在。因为声明的类型就是那个联合，Pydantic 知道要按实际的分支来导出。

### 8.6 判别联合的 JSON Schema

这是这一章和第 7 章的交汇点：

```json
"channel": {
  "discriminator": {
    "mapping": {
      "email": "#/$defs/EmailCfg",
      "push": "#/$defs/PushCfg",
      "sms": "#/$defs/SmsCfg"
    },
    "propertyName": "type"
  },
  "oneOf": [
    {"$ref": "#/$defs/SmsCfg"},
    {"$ref": "#/$defs/EmailCfg"},
    {"$ref": "#/$defs/PushCfg"}
  ],
  "title": "Channel"
}
```

三个部分：
- `"oneOf"`：**三选一**（不是 anyOf，是严格的恰好一个）；
- `"propertyName": "type"`：**用哪一列来判断**；
- `"mapping"`：**取值 → 对应哪张子表**的对照表。

每个分支的 `type` 字段在 schema 里长这样：

```json
"type": { "const": "sms", "title": "Type", "type": "string" }
```

`const` 表示「这一格只能填这个固定值」。

> 👉 **PM 视角**：`mapping` 这段就是你在 PRD 里画的那张**联动规则表**：
>
> | 选择「通知方式」 | 显示以下字段 |
> |---|---|
> | 短信 | 手机号、短信模板 |
> | 邮件 | 收件地址、主题、抄送 |
> | 推送 | 设备 token、角标数 |
>
> 一模一样。而且因为它进了 JSON Schema，**前端表单引擎可以直接读它来渲染联动表单，大模型也能理解「选了 sms 就该填 phone 和 template_id」**。你在 PRD 里画的联动逻辑，一路自动流到了前端和 AI，中间没有人肉传话。

### 8.7 列表里放判别联合

```python
class Flow(BaseModel):
    steps: list[Channel]


f = Flow.model_validate({"steps": [
    {"type": "sms", "phone": "13800138000", "template_id": "T1"},
    {"type": "push", "device_token": "tok", "badge": 3},
]})
print(f.model_dump())
print([type(s).__name__ for s in f.steps])
```

```text
{'steps': [{'type': 'sms', 'phone': '13800138000', 'template_id': 'T1'}, {'type': 'push', 'device_token': 'tok', 'badge': 3}]}
['SmsCfg', 'PushCfg']
```

> 👉 **PM 视角**：这就是**工作流编排 / 自动化规则引擎**的数据结构。「新用户注册后：① 发欢迎短信 ② 3 天后发推送 ③ 7 天后发邮件」——一个由不同类型步骤组成的列表。营销自动化、审批流配置、Agent 的多步计划，底层建模都长这样。

### 8.8 普通联合的 smart 模式

不是所有联合都需要判别器。类型完全不同的简单联合，Pydantic 会智能选择：

```python
class U(BaseModel):
    v: int | str


print(U(v="123").v, type(U(v="123").v).__name__)
print(U(v=123).v, type(U(v=123).v).__name__)
```

```text
123 str
123 int
```

传字符串就保持字符串，传整数就保持整数——**优先选"不需要转换"的那个分支**，而不是从左往右第一个能转成功的。

> ⚠️ **坑**：官方建议**尽量少用普通联合**。原因是每个用到这个字段的地方，都要先判断"这次到底是哪种类型"，代码会变得很啰嗦。如果你的目的只是"接受字符串形式的数字"，那直接写 `int` 就行（Pydantic 会自动转），不要写 `int | str`。

---

## 9. ValidationError：怎么读这份错误报告

### 9.1 它解决什么问题

校验失败时，需要一份**结构化、可编程处理**的错误报告，而不只是一句人话。

```python
class Addr(BaseModel):
    city: str
    zipcode: str = Field(pattern=r"^\d{6}$")


class Reg(BaseModel):
    name: str = Field(min_length=2)
    age: int = Field(ge=18)
    role: Literal["admin", "user"]
    addr: Addr


try:
    Reg.model_validate({"name": "A", "age": 15, "role": "boss",
                        "addr": {"zipcode": "12"}})
except ValidationError as e:
    print(e)
```

```text
5 validation errors for Reg
name
  String should have at least 2 characters [type=string_too_short, input_value='A', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/string_too_short
age
  Input should be greater than or equal to 18 [type=greater_than_equal, input_value=15, input_type=int]
    For further information visit https://errors.pydantic.dev/2.13/v/greater_than_equal
role
  Input should be 'admin' or 'user' [type=literal_error, input_value='boss', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/literal_error
addr.city
  Field required [type=missing, input_value={'zipcode': '12'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
addr.zipcode
  String should match pattern '^\d{6}$' [type=string_pattern_mismatch, input_value='12', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/string_pattern_mismatch
```

**五个错误一次报全，包括嵌套子表里的。**

### 9.2 结构化读取：e.errors()

```python
for item in err.errors():
    print(item)
```

```text
{'type': 'string_too_short', 'loc': ('name',), 'msg': 'String should have at least 2 characters', 'input': 'A', 'ctx': {'min_length': 2}, 'url': '...'}
{'type': 'greater_than_equal', 'loc': ('age',), 'msg': 'Input should be greater than or equal to 18', 'input': 15, 'ctx': {'ge': 18}, 'url': '...'}
{'type': 'literal_error', 'loc': ('role',), 'msg': "Input should be 'admin' or 'user'", 'input': 'boss', 'ctx': {'expected': "'admin' or 'user'"}, 'url': '...'}
{'type': 'missing', 'loc': ('addr', 'city'), 'msg': 'Field required', 'input': {'zipcode': '12'}, 'url': '...'}
{'type': 'string_pattern_mismatch', 'loc': ('addr', 'zipcode'), 'msg': "String should match pattern '^\\d{6}$'", 'input': '12', 'ctx': {'pattern': '^\\d{6}$'}, 'url': '...'}
```

每条错误的五个键：

| 键 | 含义 | 谁用它 |
|---|---|---|
| `type` | **错误码**，机器可读的稳定标识 | 前端做多语言映射、监控做分类统计 |
| `loc` | **位置**，一个元组，逐层定位 | 前端定位到具体输入框 |
| `msg` | 人类可读的英文描述 | 兜底展示 / 日志 |
| `input` | 用户实际传了什么 | 排查问题 |
| `ctx` | 约束的上下文（如 `{'min_length': 2}`） | **拼中文文案的关键** |

### 9.3 loc：定位到具体位置

```python
class Deep(BaseModel):
    orders: list[Reg]


try:
    Deep.model_validate({"orders": [{"name": "ok", "age": 20, "role": "user",
                                     "addr": {"city": "北京", "zipcode": "1"}}]})
except ValidationError as e:
    print(e.errors()[0]["loc"], "->", ".".join(str(x) for x in e.errors()[0]["loc"]))
```

> ⚠️ **坑（Python 本身的，不是 Pydantic 的）**：本章后面几节会接着分析这个错误对象。但 **Python 在 `except` 块结束时会自动删掉 `e` 这个变量**，块外再引用它会报 `NameError`。所以实际跑的时候要先存下来：
>
> ```python
> except ValidationError as e:
>     err = e            # ← 存进另一个变量，后面才用得到
> ```
>
> 下文示例统一用 `err` 指代这个已捕获的错误对象。

```text
('orders', 0, 'addr', 'zipcode') -> orders.0.addr.zipcode
```

`loc` 的元组里，**字符串是字段名，数字是列表下标**。`('orders', 0, 'addr', 'zipcode')` = 「第 1 条订单的地址的邮编」。

### 9.4 常见错误码速查

| `type` | 触发条件 | 建议中文文案 |
|---|---|---|
| `missing` | 必填字段没传 | 请填写{字段名} |
| `string_too_short` / `string_too_long` | 字符串长度 | 长度需在 {min}–{max} 之间 |
| `string_pattern_mismatch` | 正则不匹配 | 格式不正确 |
| `greater_than` / `greater_than_equal` | 数值下限 | 需大于（等于）{ctx.gt} |
| `less_than` / `less_than_equal` | 数值上限 | 需小于（等于）{ctx.le} |
| `int_parsing` / `float_parsing` | 无法转成数字 | 请填写数字 |
| `literal_error` | 不在选项里 | 请选择：{ctx.expected} |
| `too_short` / `too_long` | 列表长度 | 数量需在 {min}–{max} 之间 |
| `extra_forbidden` | 传了未定义的字段 | 存在不支持的参数 |
| `value_error` | 自定义校验器抛的 | 用你自己写的文案 |
| `union_tag_not_found` / `union_tag_invalid` | 判别联合的类型问题 | 请选择正确的类型 |
| `frozen_instance` | 改了不可变对象 | 该记录不允许修改 |

### 9.5 自定义错误文案

```python
class Order(BaseModel):
    qty: int

    @field_validator("qty")
    @classmethod
    def chk(cls, v):
        if v > 100:
            raise ValueError("单次下单不能超过 100 件，请联系客服走大宗采购")
        return v


try:
    Order(qty=500)
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
Value error, 单次下单不能超过 100 件，请联系客服走大宗采购
```

自定义校验器抛的 `ValueError` 会被包装成 `type='value_error'`，`msg` 前面会自动加上 `Value error, ` 前缀。

### 9.6 输出成 JSON 给前端

```python
print(err.json())                                        # 完整版
print(err.json(include_url=False, include_input=False))  # 精简版：直接就是 JSON 字符串
```

精简版：

```json
[
  {"type": "string_too_short", "loc": ["name"], "msg": "String should have at least 2 characters", "ctx": {"min_length": 2}},
  {"type": "greater_than_equal", "loc": ["age"], "msg": "Input should be greater than or equal to 18", "ctx": {"ge": 18}},
  {"type": "literal_error", "loc": ["role"], "msg": "Input should be 'admin' or 'user'", "ctx": {"expected": "'admin' or 'user'"}},
  {"type": "missing", "loc": ["addr", "city"], "msg": "Field required"},
  {"type": "string_pattern_mismatch", "loc": ["addr", "zipcode"], "msg": "String should match pattern '^\\d{6}$'", "ctx": {"pattern": "^\\d{6}$"}}
]
```

> ⚠️ **坑**：**生产环境一定要用 `include_input=False`**。`input` 字段会把用户传的原始值原样回显——如果那个值是密码、身份证号、银行卡号，就会被写进错误日志或者直接返回给前端。这是一条实实在在的数据泄露路径。

> 👉 **PM 视角**：这一章的产品价值集中在一句话：**错误报告是一份数据，不是一段文字。**
>
> 因为它是数据，所以你可以在 PRD 里提出这些要求，而且工程上都很容易实现：
> 1. **一次报全**：用户改一遍就能提交成功，而不是提交五次改五个错（Pydantic 默认就做到了）；
> 2. **精确定位**：`loc` 告诉前端在哪个输入框下面飘红，包括「第 3 行明细的手机号」这种嵌套位置；
> 3. **中文文案**：前端拿 `type` + `ctx` 拼中文，不要把 `String should have at least 2 characters` 直接怼给用户看；
> 4. **不回显敏感值**：`include_input=False`；
> 5. **可统计**：把 `type` + `loc` 打点上报，就能看出「哪个字段最容易填错」——这是优化表单设计的一手数据。第 5 点尤其值得做，它能直接告诉你表单哪里设计得不好。
>
> 建议在 PRD 的「异常处理」一节里，把这五条写成通用规范。

---

## 10. model_config / ConfigDict：整张表的全局开关

### 10.0 配置总表

配置写在类里面，用 `model_config = ConfigDict(...)`：

```python
from pydantic import ConfigDict


class M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    a: int
```

| 配置项 | 作用 | PM 直觉 |
|---|---|---|
| `extra` | 多传的字段怎么办（`ignore`/`forbid`/`allow`） | 表单能不能多填 |
| `frozen` | 创建后不许改 | 只读记录 / 快照 |
| `validate_assignment` | 每次赋值都重新校验 | 修改也要过审 |
| `populate_by_name` | 别名和原名都认 | 兼容新旧字段名（2.11+ 推荐改用 `validate_by_name` + `validate_by_alias`，本项 v3 将废弃） |
| `str_strip_whitespace` | 所有字符串自动去首尾空格 | 全局输入清洗 |
| `str_to_lower` / `str_to_upper` | 所有字符串统一大小写 | 全局规范化 |
| `use_enum_values` | 存枚举的值而不是枚举对象 | 简化存储 |
| `title` | 这张表的显示名 | 表名（进 schema） |
| `validate_default` | 默认值也要过校验 | 默认值也要合规 |
| `arbitrary_types_allowed` | 允许用 Pydantic 不认识的类型 | 逃生舱 |
| `alias_generator` | 批量生成别名（如全转驼峰） | 一键切换命名风格 |

### 10.1 extra：多传的字段怎么办

**它解决什么问题**：外部传了模型里没定义的字段，是无视、报错、还是留着？

```python
class Ignore(BaseModel):
    model_config = ConfigDict(extra="ignore")     # 默认
    a: int


class Forbid(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: int


class Allow(BaseModel):
    model_config = ConfigDict(extra="allow")
    a: int


print("ignore:", Ignore(a=1, b=2).model_dump())
try:
    Forbid(a=1, b=2)
except ValidationError as e:
    print("forbid:", e.errors()[0]["type"], e.errors()[0]["loc"])
al = Allow(a=1, b=2)
print("allow :", al.model_dump(), "| al.b =", al.b)
```

```text
ignore: {'a': 1}
forbid: extra_forbidden ('b',)
allow : {'a': 1, 'b': 2} | al.b = 2
```

| 取值 | 行为 | 什么时候用 |
|---|---|---|
| `"ignore"`（默认） | 悄悄丢掉 | 对接第三方，上游可能随时加字段 |
| `"forbid"` | 报错 | 内部接口，希望严格对齐；防止字段名拼错 |
| `"allow"` | 原样保留，能读能导出 | 需要透传未知字段（如网关、代理层） |

> 👉 **PM 视角**：这是一条**接口治理策略**，不同场景该选不同的值：
> - **对内接口** → `forbid`。前端把 `phoneNumber` 拼成 `phonNumber` 时立刻报错，而不是让这个字段悄悄丢失，然后过两天客服收到"我明明填了手机号"的投诉。
> - **对外/第三方回调** → `ignore`（默认）。对方升级加了新字段，你的系统不该因此挂掉。
> - **网关/中转层** → `allow`。你不理解的字段也要原样传下去。
>
> 这三条可以直接写进你们的接口规范。

### 10.2 frozen：只读

```python
class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)
    a: int


fz = Frozen(a=1)
try:
    fz.a = 2
except ValidationError as e:
    print(e.errors()[0]["type"], e.errors()[0]["msg"])
print("可以做 dict 的 key:", {fz: "ok"}[Frozen(a=1)])
```

```text
frozen_instance Instance is frozen
可以做 dict 的 key: ok
```

`frozen=True` 还有个附带效果：对象变得可哈希，可以当字典的键、放进集合。

> 👉 **PM 视角**：`frozen` 对应产品里的「**快照 / 存证 / 不可篡改记录**」。
> - 订单**成交时**的价格快照——之后商品调价，历史订单里的价格不能跟着变；
> - 合同签署后的条款；
> - 审计日志。
>
> 在 PRD 里写「历史订单显示下单时的价格」时，背后就是这个概念。用 `frozen=True` 把"不可修改"这条规则固化在代码里，比靠程序员自觉不去改它可靠得多。

### 10.3 validate_assignment

见 2.6 和 5.9 节。默认关闭，开了之后每次赋值都重新走一遍校验（有一点性能成本，但通常可以忽略）。

### 10.4 populate_by_name

见 3.9 节。让别名和原字段名都能作为输入。

### 10.5 全局字符串清洗

```python
class Clean(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, str_to_lower=True)
    email: str


print(repr(Clean(email="  Foo@Bar.COM ").email))
```

```text
'foo@bar.com'
```

> 👉 **PM 视角**：把「去空格」「邮箱统一小写」提升到**整张表的默认规则**，而不是每个字段单独设。这在做「用户注册」这类表单时很实用——邮箱大小写不敏感、账号不允许首尾空格，是通用规则而不是某一个字段的特例。
>
> ⚠️ 但要小心 `str_to_lower`：如果这张表里有「密码」或「区分大小写的编码」字段，全局转小写会出事。这类配置适合用在字段用途单一的表上。

### 10.6 use_enum_values

```python
from enum import Enum


class Status(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class E1(BaseModel):
    s: Status


class E2(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    s: Status


print("默认           :", repr(E1(s="draft").s))
print("use_enum_values:", repr(E2(s="draft").s))
```

```text
默认           : <Status.DRAFT: 'draft'>
use_enum_values: 'draft'
```

开了之后，字段里存的直接是字符串 `'draft'`，而不是枚举对象。好处是存数据库、转 JSON 更省事；坏处是失去了枚举对象的类型提示和方法。

### 10.7 其他常用配置

```python
class Misc(BaseModel):
    model_config = ConfigDict(
        title="配置示例",                  # 进 JSON Schema 的表名
        populate_by_name=True,            # 别名和原名都认
        validate_default=True,            # 默认值也要过校验
        arbitrary_types_allowed=True,     # 允许 Pydantic 不认识的类型
    )
    a: int = Field(alias="A", default=1)


print(Misc(a=5), Misc(A=6))
print(Misc.model_json_schema()["title"])
```

```text
a=5 a=6
配置示例
```

**`validate_default=True`** 值得单独说：默认情况下，默认值是**不校验**的。也就是说你可以写 `age: int = Field(ge=18, default=0)`，这个明显违规的默认值 Pydantic 不会拦。开了 `validate_default` 才会。

> 👉 **PM 视角**：`title` 会直接进 JSON Schema，也就是会出现在 API 文档和给大模型的说明书里。**给表起个中文名比让它显示 `OrderReq` 要友好得多**——尤其是给大模型看的时候，中文表名 + 中文字段说明，模型的理解准确率会更高。

### 10.8 配置也可以继承

子类会继承父类的 `model_config`，也可以覆盖其中的某几项。所以团队可以定一个"基类"，把公司规范（比如统一 `extra="forbid"` + `str_strip_whitespace=True`）写在里面，所有业务模型继承它。

> 👉 **PM 视角**：这就是**技术规范的落地方式**。与其在 wiki 上写一条「所有接口必须开启严格模式」然后靠 code review 抓，不如提供一个基类让大家继承——**把规范变成默认行为，而不是变成纪律要求**。这个思路在产品设计上同样适用。

---

## 11. TypeAdapter：给「不是表」的东西做校验

### 11.1 它解决什么问题

前面所有能力都挂在 `BaseModel` 上。但有时候你要校验的**不是一张表**：

- 接口返回的是一个**数组**：`[{...}, {...}]`
- 配置项是一个**字典**：`{"key": "value"}`
- 你只想校验**一个数字**在不在范围内

这时候没必要为它包一层模型，用 `TypeAdapter` 直接给任意类型做校验。

```python
from pydantic import TypeAdapter


ta_list = TypeAdapter(list[int])
print(ta_list.validate_python(["1", 2, "3"]))     # 一样会转换
try:
    ta_list.validate_python(["a"])
except ValidationError as e:
    print(e)
```

```text
[1, 2, 3]
1 validation error for list[int]
0
  Input should be a valid integer, unable to parse string as an integer [type=int_parsing, input_value='a', input_type=str]
```

注意错误里的 `0` —— 列表下标。

### 11.2 校验模型的列表

最常见的用途：接口返回的是一个数组。

```python
class Addr(BaseModel):
    city: str
    zipcode: str = Field(pattern=r"^\d{6}$")


ta = TypeAdapter(list[Addr])
print(ta.validate_json('[{"city":"上海","zipcode":"200000"}]'))
```

```text
[Addr(city='上海', zipcode='200000')]
```

字典也行：

```python
ta_dict = TypeAdapter(dict[str, Addr])
print(ta_dict.validate_python({"home": {"city": "北京", "zipcode": "100000"}}))
```

```text
{'home': Addr(city='北京', zipcode='100000')}
```

### 11.3 校验带约束的单个值

```python
Score = Annotated[int, Field(ge=0, le=100)]
ta_score = TypeAdapter(Score)

print(ta_score.validate_python(88))
try:
    ta_score.validate_python(120)
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
88
Input should be less than or equal to 100
```

### 11.4 TypeAdapter 也能出 schema 和序列化

```python
print(json.dumps(TypeAdapter(list[Addr]).json_schema(), indent=2, ensure_ascii=False))
print(ta_list.dump_json([1, 2, 3]))
```

```json
{
  "$defs": {
    "Addr": {
      "properties": {
        "city": {"title": "City", "type": "string"},
        "zipcode": {"pattern": "^\\d{6}$", "title": "Zipcode", "type": "string"}
      },
      "required": ["city", "zipcode"],
      "title": "Addr", "type": "object"
    }
  },
  "items": {"$ref": "#/$defs/Addr"},
  "type": "array"
}
```

```text
b'[1,2,3]'
```

`TypeAdapter` 的方法和 `BaseModel` 是对应的：

| BaseModel | TypeAdapter |
|---|---|
| `Model.model_validate(x)` | `ta.validate_python(x)` |
| `Model.model_validate_json(s)` | `ta.validate_json(s)` |
| `obj.model_dump()` | `ta.dump_python(obj)` |
| `obj.model_dump_json()` | `ta.dump_json(obj)` |
| `Model.model_json_schema()` | `ta.json_schema()` |

### 11.5 也能校验 TypedDict 和 dataclass

```python
from typing_extensions import TypedDict   # Python < 3.12 必须用这个
from dataclasses import dataclass


class TD(TypedDict):
    a: int
    b: str


print(TypeAdapter(TD).validate_python({"a": "1", "b": "x"}))


@dataclass
class DC:
    a: int


print(TypeAdapter(DC).validate_python({"a": "9"}))
```

```text
{'a': 1, 'b': 'x'}
DC(a=9)
```

> ⚠️ **坑**：在 Python 3.11 及以下，必须用 `typing_extensions.TypedDict`，用标准库的 `typing.TypedDict` 会直接报错：
>
> ```text
> pydantic.errors.PydanticUserError: Please use `typing_extensions.TypedDict`
> instead of `typing.TypedDict` on Python < 3.12.
> ```
>
> 这是实测踩到的，报错信息本身写得很清楚，照做即可。

> 👉 **PM 视角**：`TypeAdapter` 的存在说明了 Pydantic 的一个设计思想——**校验能力和"要不要建一张表"是解耦的**。
>
> 对应到产品上：你不需要为了"检查一批手机号是否合法"而先建一个"手机号表"。**校验规则应该能独立于数据结构被复用。** 在实际项目里，`TypeAdapter` 最常见的场景是：批量导入（校验一整个列表）、配置文件解析（校验一个字典）、以及给大模型的输出做校验（有时模型返回的就是一个数组，不是一个对象）。
>
> 最后一个场景在本书后面会遇到：让模型「提取所有提到的商品」，返回的自然是一个列表，这时候用的就是 `TypeAdapter(list[Product])`。

---

## 12. 常见坑清单

把全文的坑集中到一处，方便回头查。

| # | 坑 | 现象 | 正确做法 | 章节 |
|---|---|---|---|---|
| 1 | 看资料看到 V1 的 API | `parse_obj` / `@validator` 报错或过时 | 认准 V2：`model_validate` / `@field_validator` | 0 |
| 2 | 默认不校验赋值 | 创建后随便改属性都不报错 | `ConfigDict(validate_assignment=True)` | 2.6 |
| 3 | `x: int = Field(...)` 以为是选填 | 一直报 `missing` | 没写 `default=` 就是必填；或用 Annotated 形式 | 3.6 |
| 4 | 可变默认值 | 多个实例共享同一个列表 | `Field(default_factory=list)` | 3.5 |
| 5 | 设了 alias 后原名不认了 | 用原名传参报 `missing` | `populate_by_name=True`（2.11+ 推荐 `validate_by_name=True`） | 3.9 |
| 6 | `Optional` ≠ 选填 | `x: str \| None` 仍然必填 | 要选填得写 `= None` | 4.2 |
| 7 | 枚举 dump 出来是对象不是字符串 | `json.dumps` 报错 | `mode="json"` 或 `use_enum_values=True` | 4.4 |
| 8 | 金额用 `float` | 累加出现 0.30000000000000004 | 用 `Decimal` | 4.1 |
| 9 | 布尔列不认「是/Y」 | Excel 导入大面积失败 | PRD 里明确布尔列接受的写法 | 4.1 |
| 10 | 校验器忘了 `return` | 字段变成 `None` | 一定要把值还回去 | 5.1 |
| 11 | 校验器里清洗和判断顺序反了 | 小写输入被误拒 | 先规整再判断 | 5.1 |
| 12 | `model_validator(before)` 假设一定是 dict | 偶发崩溃 | 先 `isinstance(data, dict)` | 5.7 |
| 13 | `model_dump()` 直接喂 `json.dumps` | `datetime` 不可序列化 | `mode="json"` 或 `model_dump_json()` | 6.1 |
| 14 | 继承 + 父类型声明导致字段消失 | 静默丢字段，最难查 | 用判别联合；应急用 `serialize_as_any=True` | 6.5 |
| 15 | 未知字段被静默丢弃 | 字段名拼错也不报错 | 对内接口开 `extra="forbid"` | 6.6 |
| 16 | `model_validator` 的业务规则不进 schema | 大模型看不到这条规则 | 写进 `description` + 事后校验重试 | 7.9 |
| 17 | 错误报告回显敏感输入 | 密码进日志 | `errors(include_input=False)` | 9.6 |
| 18 | 默认值不参与校验 | 违规默认值溜过去 | `validate_default=True` | 10.7 |
| 19 | 普通联合报错难读 | 所有分支的错误全报一遍 | 加判别器 | 8.2 |
| 20 | Python < 3.12 用 `typing.TypedDict` | 直接报 PydanticUserError | 用 `typing_extensions.TypedDict` | 11.5 |
| 21 | `deprecated` 挂在联合的单个分支上 | 不生效，只有警告 | 挂在最外层：`Annotated[int \| None, Field(...)]` | 3.7 |

---

## 13. 速查表

### 13.1 常用 API

| 我想…… | 写法 |
|---|---|
| 定义一张表 | `class X(BaseModel):` |
| 从 dict 校验 | `X.model_validate(d)` |
| 从 JSON 字符串校验 | `X.model_validate_json(s)` |
| 转成 dict | `x.model_dump()` |
| 转成可 JSON 化的 dict | `x.model_dump(mode="json")` |
| 转成 JSON 字符串 | `x.model_dump_json(indent=2)` |
| 生成说明书 | `X.model_json_schema()` |
| 复制并改几个值 | `x.model_copy(update={...})` |
| 看有哪些字段 | `X.model_fields` |
| 看有哪些计算字段 | `X.model_computed_fields` |
| 校验非模型类型 | `TypeAdapter(list[int]).validate_python(v)` |

### 13.2 从 PRD 到代码的对照表

| PRD 里写 | Pydantic 里写 |
|---|---|
| 必填 | 不写默认值 |
| 选填 | `= None` 或 `= 默认值` |
| 必填但可为空 | `x: str \| None`（不给默认值） |
| 文本，2–20 字 | `Field(min_length=2, max_length=20)` |
| 数字，大于 0 | `Field(gt=0)` |
| 数字，0–100 | `Field(ge=0, le=100)` |
| 下拉框：A/B/C | `Literal["A","B","C"]` |
| 手机号格式 | `Field(pattern=r"^1\d{10}$")` |
| 金额 | `Decimal` + `Field(gt=0)` |
| 日期 | `date` |
| 明细列表，最多 20 条 | `list[Item] = Field(max_length=20)` |
| 标签，去重 | `set[str]` |
| 子表 / 嵌套对象 | 另一个 `BaseModel` |
| 系统自动生成 | `Field(default_factory=...)` |
| 系统计算得出 | `@computed_field` |
| 字段说明 | `Field(description="……")` |
| 内外字段名不同 | `Field(alias="外部名")` |
| 单字段业务规则 | `@field_validator` |
| 跨字段规则 | `@model_validator(mode="after")` |
| 超过阈值走审批 | `@model_validator(mode="after")` 先算再判 |
| 选了 A 才显示 B 组字段 | 判别联合 `Field(discriminator="type")` |
| 不允许多传字段 | `ConfigDict(extra="forbid")` |
| 创建后不可修改 | `ConfigDict(frozen=True)` |
| 输入自动去空格 | `ConfigDict(str_strip_whitespace=True)` |

### 13.3 三张图回顾全章

**数据流**：

```text
外部数据 ──▶ [before 校验器] ──▶ [类型转换 + Field 约束] ──▶ [after 校验器]
                                                                  │
                                                                  ▼
                                                          合法的模型对象
                                                                  │
                        ┌─────────────────────────────────────────┼─────────────────────┐
                        ▼                                         ▼                     ▼
                  model_dump()                            model_dump_json()    model_json_schema()
                   给 Python                                  给接口              给文档/前端/大模型 ★
```

**一张表由什么组成**：

```text
class Order(BaseModel):
    model_config = ConfigDict(...)          ← 整表开关（第 10 章）

    price: float = Field(gt=0, ...)         ← 类型（第 4 章）+ 约束和说明（第 3 章）
    channel: Annotated[A|B, Field(
        discriminator="type")]              ← 分支字段（第 8 章）

    @field_validator("price")               ← 单字段规则（5.1）
    @model_validator(mode="after")          ← 跨字段规则、先算再判（5.5、5.6）
    @computed_field                         ← 计算字段（6.3）
    @field_serializer("price")              ← 导出格式（6.4）
```

**PM 该关心哪几个参数**：

```text
优先级最高 ★★★   Field(description=...)     决定 AI 填得对不对、文档写得清不清楚
优先级高   ★★     Literal / Enum             决定枚举值全链路一致
优先级高   ★★     必填 / 选填 / 可为空        三者含义不同，评审时要说清
优先级高   ★★     gt / ge、lt / le           边界值，测试用例最容易出问题的地方
优先级中   ★       extra 策略                 对内 forbid、对外 ignore
优先级中   ★       computed_field            区分「用户填」和「系统算」
```

---

## 14. 小结：这一部分你需要带走什么

如果只记三句话：

1. **Pydantic 是「把 PRD 字段规则表变成可执行代码」的库。** 它站在系统的入口，只放行符合规则的数据，并且一次性报全所有错误。

2. **`model_json_schema()` 是它最被低估的能力。** 你画的表可以自动变成一份机器可读的说明书，同时供给 API 文档、前端表单和大模型。这是本书后面 Pydantic AI 结构化输出的底层机制。

3. **`Field(description=...)` 是产品经理在 AI 项目里最大的杠杆。** 它不再是注释，它是提示词的一部分，直接决定模型填得对不对。

下一部分我们会看到：当把这些模型交给 Pydantic AI，它如何驱动大模型按你定义的表格，稳定地输出结构化结果。
