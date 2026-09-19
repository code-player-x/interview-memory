# 设计模式 / 面向对象

> 题目数量：**8** ｜ 生成时间：2026-09-19 08:40:12 ｜ 源文件：`questions-bank.json`

本题库为问答题，「选项」一栏统一标注为不适用。

---

## 1. 单例和全局变量的区别

> 原题 ID：`q0976` ｜ 原分类：概念基础 ｜ 来源：飞书知识库·设计模式知识库

### 题干

单例和全局变量的区别

### 选项

（本题为问答题，原始题库无选项字段）

### 答案

- 单例是一种更优雅、更可控的全局访问方式，适合需要全局唯一实例的场景。

### 解析

- 单例是一种更优雅、更可控的全局访问方式，适合需要全局唯一实例的场景。可以延迟初始化，节省资源。
- 全局变量虽然简单，但缺乏封装性和可控性，容易导致代码质量下降。
- 在后端开发中，优先使用单例模式来管理全局资源，避免直接使用全局变量。

单例模式有 饿汉式 和 懒汉式 两种实现，个人其实更倾向于饿汉式的实现，简单，并且可以将问题及早暴露，懒汉式虽然支持延迟加载，但是这只是把冷启动时间放到了第一次使用的时候，并没有本质上解决问题，并且为了实现懒汉式还不可避免的需要加锁。

**雷区**

- 在后端开发中，优先使用单例模式来管理全局资源，避免直接使用全局变量。

### 难度

★★☆

### 标签

`设计模式` `设计模式七大原则`

---

## 2. 饿汉模式

> 原题 ID：`q0977` ｜ 原分类：概念基础 ｜ 来源：飞书知识库·设计模式知识库

### 题干

饿汉模式

### 选项

（本题为问答题，原始题库无选项字段）

### 答案

- 在 init 函数中直接初始化 singleton 实例。

### 解析

- 在 init 函数中直接初始化 singleton 实例。
- 这种方式在程序启动时就会创建单例对象，而不是在第一次调用 GetInstance 时才创建。
- 优点是线程安全（因为 Go 的 init 函数在包初始化时执行，且只会执行一次）。
- 缺点是如果单例对象的初始化成本较高，可能会影响程序启动性能。
- 适用于对象初始化成本低，且不需要延迟加载

Go
// Singleton 饿汉式单例
type Singleton struct{}

var singleton *Singleton

func init() {
singleton = &Singleton{}
}

// GetInstance 获取实例
func GetInstance() *Singleton {
return singleton
}

### 难度

★★☆

### 标签

`设计模式` `单例模式`

---

## 3. 懒汉模式（双重检测）

> 原题 ID：`q0978` ｜ 原分类：概念基础 ｜ 来源：飞书知识库·设计模式知识库

### 题干

懒汉模式（双重检测）

### 选项

（本题为问答题，原始题库无选项字段）

### 答案

Go

### 解析

Go
var (
lazySingleton *Singleton
once          = &sync.Once{}
)

// GetLazyInstance 懒汉式
func GetLazyInstance() *Singleton {
if lazySingleton == nil {
once.Do(func() {
lazySingleton = &Singleton{}
})
}
return lazySingleton
}

工厂模式的核心目的就是通过引入工厂类，帮助我们屏蔽后端创建对象的细节，让客户端只面向工厂完成数据对象的构建工作

[GO语言实现设计模式-工厂模式(比较清晰-推荐)](https://isekiro.com/go%E8%AF%AD%E8%A8%80%E5%AE%9E%E7%8E%B0%E8%AE%BE%E8%AE%A1%E6%A8%A1%E5%BC%8F-%E5%B7%A5%E5%8E%82%E6%A8%A1%E5%BC%8F/)

### 难度

★★☆

### 标签

`设计模式` `单例模式`

---

## 4. 简单工厂

> 原题 ID：`q0979` ｜ 原分类：概念基础 ｜ 来源：飞书知识库·设计模式知识库

### 题干

简单工厂

### 选项

（本题为问答题，原始题库无选项字段）

### 答案

[23种设计模式之工厂模式](https://www.bilibili.com/video/BV1He4y1X7zp/?spm_id_from=333.337.search-card.all.click&vd_source=071e9889

### 解析

[23种设计模式之工厂模式](https://www.bilibili.com/video/BV1He4y1X7zp/?spm_id_from=333.337.search-card.all.click&vd_source=071e98898557028cf1e9013c33c721b3)

由于 Go 本身是没有构造函数的，一般而言我们采用 NewName  的方式创建对象/接口，当它返回的是接口的时候，其实就是简单工厂模式

go
type Fruit interface {
Show()
}
type Apple struct {
}
func (a *Apple) Show() {
fmt.Println("I am Apple")
}

type Banana struct {
}
func (a *Banana) Show() {
fmt.Println("I am Banana")
}

type Pear struct {
}
func (a *Pear) Show() {
fmt.Println("I am Pear")
}

type Factory struct {
}
func (f *Factory) CreateFruit(kind string) Fruit {
var fruit Fruit
switch kind {
case "apple":
fruit = new(Apple)
case "banana":
fruit = new(Banana)
case "pear":
fruit = new(Pear)
default:
fruit = new(Apple)
}
return fruit
}

func main() {
fac := new(Factory)
apple := fac.CreateFruit("apple")
apple.Show()
banana := fac.CreateFruit("banana")
banana.Show()
pear := fac.CreateFruit("pear")
pear.Show()
}
//I am Apple
//I am Banana
//I am Pear

### 难度

★★☆

### 标签

`设计模式` `工厂模式`

---

## 5. 工厂方法

> 原题 ID：`q0980` ｜ 原分类：概念基础 ｜ 来源：飞书知识库·设计模式知识库

### 题干

工厂方法

### 选项

（本题为问答题，原始题库无选项字段）

### 答案

当对象的创建逻辑比较复杂，不只是简单的 new 一下就可以，而是要组合其他类对象，做各种初始化操作的时候，推荐使用工厂方法模式，将复杂的创建逻辑拆分到多个工厂类中，让每个工厂类都不至于过于复杂

### 解析

当对象的创建逻辑比较复杂，不只是简单的 new 一下就可以，而是要组合其他类对象，做各种初始化操作的时候，推荐使用工厂方法模式，将复杂的创建逻辑拆分到多个工厂类中，让每个工厂类都不至于过于复杂

go
type Fruit interface {
Show()
}

type Factory interface {
CreateFruit() Fruit
}
type Apple struct {
}

func (a *Apple) Show() {
fmt.Println("I am Apple")
}

type Banana struct {
}

func (a *Banana) Show() {
fmt.Println("I am Banana")
}

type Pear struct {
}

func (a *Pear) Show() {
fmt.Println("I am Pear")
}

type AppleFactory struct {
}

func (a *AppleFactory) CreateFruit() Fruit {
return new(Apple)
}

type BananaFactory struct {
}

func (a *BananaFactory) CreateFruit() Fruit {
return new(Banana)
}

type PearFactory struct {
}

func (a *PearFactory) CreateFruit() Fruit {
return new(Pear)
}

func main() {
appleFac := new(AppleFactory)
apple := appleFac.CreateFruit()
apple.Show()
}

### 难度

★★☆

### 标签

`设计模式` `工厂模式`

---

## 6. 抽象工厂

> 原题 ID：`q0981` ｜ 原分类：概念基础 ｜ 来源：飞书知识库·设计模式知识库

### 题干

抽象工厂

### 选项

（本题为问答题，原始题库无选项字段）

### 答案

抽象工厂模式（Abstract Factory Pattern）是一种创建型设计模式，它的主要目的是提供一个接口，用于创建一系列相关或相互依赖的对象，而无需指定它们的具体类。

### 解析

抽象工厂模式（Abstract Factory Pattern）是一种创建型设计模式，它的主要目的是提供一个接口，用于创建一系列相关或相互依赖的对象，而无需指定它们的具体类。抽象工厂模式的核心思想是将对象的创建与使用分离，使得系统更加灵活、可扩展，并符合开闭原则。

为什么需要抽象工厂模式？

1. 解决复杂对象的创建问题

- 当一个系统需要创建一系列相关或相互依赖的对象时，如果直接使用简单工厂或工厂方法模式，可能会导致代码重复或难以维护。
- 抽象工厂模式通过提供一个统一的接口来创建一组对象，避免了客户端直接依赖具体的实现类。
2. 支持产品族的创建

- 抽象工厂模式特别适合用于创建“产品族”（即一组相关的产品）。例如，在一个 GUI 库中，可能需要创建一组与特定操作系统风格相关的控件（如按钮、文本框、下拉框等）。
- 如果没有抽象工厂模式，客户端代码需要显式地创建每个具体的控件，导致代码与具体实现紧密耦合。
3. 提高代码的可扩展性

- 抽象工厂模式允许系统在不修改现有代码的情况下引入新的产品族。例如，如果需要支持一个新的操作系统风格，只需添加一个新的工厂实现类，而不需要修改客户端代码。
4. 符合开闭原则

- 开闭原则要求软件实体（类、模块、函数等）对扩展开放，对修改关闭。
- 抽象工厂模式通过将对象的创建逻辑封装在工厂类中，使得系统可以轻松扩展新的产品族，而无需修改现有代码。
5. 降低客户端与具体实现的耦合

- 客户端代码只需要依赖抽象工厂接口和抽象产品接口，而不需要知道具体的实现类。这使得系统更加灵活，易于维护和测试。

抽象工厂模式适用于以下场景：

- 系统需要创建一组相关或相互依赖的对象。
- 系统需要支持多个产品族，并且希望客户端代码与具体实现解耦。
- 系统需要符合开闭原则，能够轻松扩展新的产品族。

Go
package main

import "fmt"

// 抽象产品：按钮
type Button interface {
Render()
}

// 抽象产品：文本框
type TextBox interface {
Display()
}

// 抽象工厂
type GUIFactory interface {
CreateButton() Button
CreateTextBox() TextBox
}

// 具体产品：Windows 按钮
type WindowsButton struct{}

func (w WindowsButton) Render() {
fmt.Println("Render a button in Windows style")
}

// 具体产品：Windows 文本框
type WindowsTextBox struct{}

func (w WindowsTextBox) Display() {
fmt.Println("Display a text box in Windows style")
}

// 具体工厂：Windows 工厂
type WindowsFactory struct{}

func (w WindowsFactory) CreateButton() Button {
return WindowsButton{}
}

func (w WindowsFactory) CreateTextBox() TextBox {
return WindowsTextBox{}
}

// 具体产品：macOS 按钮
type MacOSButton struct{}

func (m MacOSButton) Render() {
fmt.Println("Render a button in macOS style")
}

// 具体产品：macOS 文本框
type MacOSTextBox struct{}

func (m MacOSTextBox) Display() {
fmt.Println("Display a text box in macOS style")
}

// 具体工厂：macOS 工厂
type MacOSFactory struct{}

func (m MacOSFactory) CreateButton() Button {
return MacOSButton{}
}

func (m MacOSFactory) CreateTextBox() TextBox {
return MacOSTextBox{}
}

// 客户端代码
func CreateUI(factory GUIFactory) {
button := factory.CreateButton()
textBox := factory.CreateTextBox()

button.Render()
textBox.Display()
}

func main() {
// 创建 Windows 风格的 UI
windowsFactory := WindowsFactory{}
CreateUI(windowsFactory)

// 创建 macOS 风格的 UI
macOSFactory := MacOSFactory{}
CreateUI(macOSFactory)
}

[设计模式-策略模式(Strategy Pattern)](https://www.bilibili.com/video/BV1454y187Er/?spm_id_from=333.1391.0.0&vd_source=071e98898557028cf1e9013c33c721b3)

策略模式（Strategy Pattern）是一种行为型设计模式，它的主要目的是定义一系列算法，将每个算法封装起来，并使它们可以互相替换。策略模式的核心思想是将算法的使用与实现分离，使得算法可以独立于客户端而变化。

### 为什么需要策略模式？

1. 避免条件语句的复杂性

- 当一个类中有多个条件分支（如 if-else 或 switch-case）来决定使用哪种算法时，代码会变得难以维护和扩展。
- 策略模式通过将每个算法封装到独立的类中，避免了复杂的条件语句。
2. 提高代码的可扩展性

- 如果需要添加新的算法，只需添加一个新的策略类，而不需要修改现有的代码。
- 这符合开闭原则（对扩展开放，对修改关闭）。
3. 分离关注点

- 策略模式将算法的实现与使用分离，使得客户端代码只需要关注如何选择策略，而不需要关心算法的具体实现。
4. 提高代码的可维护性

- 每个策略类只负责一个算法，代码更加清晰和易于理解。
- 修改某个算法不会影响其他算法或客户端代码。
5. 支持运行时动态切换算法

- 策略模式允许在运行时动态地切换算法，而不需要在代码中硬编码具体的选择逻辑。

### 策略模式的优点

1. 避免条件语句：将算法封装到独立的类中，避免了复杂的条件分支。
2. 提高代码的可扩展性：添加新的算法只需添加新的策略类，无需修改现有代码。
3. 分离关注点：算法的实现与使用分离，代码更加清晰。
4. 支持动态切换算法：可以在运行时动态地切换算法。

---

### 策略模式的缺点

1. 增加了类的数量：每个算法都需要一个独立的策略类，可能会增加类的数量。
2. 客户端需要了解策略类：客户端需要知道有哪些策略类，并选择合适的策略。

### 策略模式的应用场景

策略模式特别适用于需要多种算法实现并希望灵活扩展的场景。

1. 多种算法实现：当一个系统需要在多种算法之间动态切换时，例如排序算法、支付方式、压缩算法等。【经典场景：地图导航中选择不同的交通方式，会生成不同的行程时间预测、跨国app中i18n的多语言适配】
2. 避免条件分支：当一个类中有多个条件分支来决定使用哪种算法时，可以使用策略模式来简化代码。
3. 需要灵活扩展：当系统需要支持新的算法，并且希望在不修改现有代码的情况下扩展时。

Go
// 策略接口：支付方式
type PaymentStrategy interface {
Pay(amount float64)
}

// 具体策略：信用卡支付
type CreditCardPayment struct{}

func (c CreditCardPayment) Pay(amount float64) {
fmt.Printf("Paid %.2f via Credit Card\n", amount)
}

// 具体策略：支付宝支付
type AlipayPayment struct{}

func (a AlipayPayment) Pay(amount float64) {
fmt.Printf("Paid %.2f via Alipay\n", amount)
}

// 具体策略：微信支付
type WechatPayment struct{}

func (w WechatPayment) Pay(amount float64) {
fmt.Printf("Paid %.2f via Wechat Pay\n", amount)
}

// 上下文类：支付上下文
type PaymentContext struct {
strategy PaymentStrategy
}

func (p *PaymentContext) SetStrategy(strategy PaymentStrategy) {
p.strategy = strategy
}

func (p *PaymentContext) ExecutePayment(amount float64) {
p.strategy.Pay(amount)
}

// 客户端代码
func main() {
context := PaymentContext{}

// 使用信用卡支付
context.SetStrategy(CreditCardPayment{})
context.ExecutePayment(100.0)

// 使用支付宝支付
context.SetStrategy(AlipayPayment{})
context.ExecutePayment(200.0)

// 使用微信支付
context.SetStrategy(WechatPayment{})
context.ExecutePayment(300.0)
}

**雷区**

- 抽象工厂模式通过提供一个统一的接口来创建一组对象，避免了客户端直接依赖具体的实现类。；- 策略模式通过将每个算法封装到独立的类中，避免了复杂的条件语句。

### 难度

★★☆

### 标签

`设计模式` `工厂模式`

---

## 7. 解决方案：我们没采用简单的全局单例Client，而是设计了按目标站点分组的连接池

> 原题 ID：`q1752` ｜ 原分类：概念基础 ｜ 来源：全平台面经采集(2026-09)·juejin

### 题干

解决方案：我们没采用简单的全局单例Client，而是设计了按目标站点分组的连接池

### 选项

（本题为问答题，原始题库无选项字段）

### 答案

把 HTTP Client 按目标站点（host/域名）分组做成连接池，而不是全局单例，核心是为了隔离不同站点的连接资源、避免相互拖累，并让每个站点独立控制并发、超时与连接复用。

### 解析

先讲背景：HTTP 客户端（如 Go 的 http.Client、Java 的 HttpClient/OkHttp、Python 的 requests.Session）底层都维护一个连接池，复用 TCP 连接（Keep-Alive）能省掉三次握手、TLS 握手和慢启动的开销。

为什么不用全局单例 Client？
1) 全局单例意味着所有目标站点共享同一个连接池和同一套参数（最大连接数、超时、重试、代理、TLS 配置）。但不同站点的特性差异很大：A 站点延迟高、B 站点 QPS 高、C 站点需要特殊证书或代理。共享一个池会出现“吵闹邻居”问题——某个慢站点把连接占满，其他站点请求排队甚至超时。
2) 全局单例难以做精细治理：无法按站点限流、熔断、统计成功率/延迟，也无法给不同站点配不同的超时和重试策略。
3) 连接复用是按 host 隔离的（HTTP/1.1 连接不能跨 host 复用），全局单例只是把多个 host 的池塞在一个对象里，管理粒度粗。

按站点分组连接池的做法：
- 以目标站点（scheme+host+port，或业务标识）为 key，维护一个 Client/连接池实例的映射（如 ConcurrentHashMap + computeIfAbsent，或带过期的缓存）。
- 每个池独立配置：最大空闲连接、最大总连接、每 host 连接上限、连接存活时间、空闲回收时间、超时、重试、代理、TLS。
- 配合按站点的限流、熔断、指标（QPS、P99、错误率），实现故障隔离。

通俗类比：全局单例 Client 像“全公司共用一个电话总机”，谁都能打，但一个话痨占线，所有人都打不出去；按站点分组像“每个合作方一条专线”，互不影响，还能按对方特点配不同线路和通话时长。

适用场景：需要访问多个第三方服务/开放平台、每个站点 SLA 和限流策略不同、需要故障隔离和精细化监控的网关、聚合服务、爬虫/数据采集、支付/风控等对稳定性要求高的系统。

实现要点：key 要归一化（域名小写、默认端口、是否含 path）；池要有上限和淘汰（LRU/过期），避免站点无限增长导致内存泄漏；Client 本身线程安全，可复用，但池的创建要防并发重复；关闭时要优雅释放连接。

**加分点**

1) 能提到连接复用的底层约束：HTTP/1.1 连接与 host 绑定，HTTP/2 虽支持多路复用但连接仍按 origin 建立，所以按站点分组天然契合协议。
2) 能说出 Go net/http 的 Transport 里 MaxIdleConnsPerHost 默认只有 2，全局单例下高并发访问同一站点很容易成为瓶颈，需要按站点调大；Java OkHttp 的 ConnectionPool 默认 5 个空闲连接、5 分钟回收，也可按站点定制。
3) 能提到“连接池不是越大越好”：连接过多会增加服务端和客户端内存、FD 消耗，还可能触发对端限流；要结合站点限流和压测定容量。
4) 能提到与熔断/隔离舱（bulkhead）模式结合：每个站点一个信号量/线程池，慢站点不拖垮整体，类似 Hystrix 的线程池隔离。
5) 能提到动态配置与热更新：站点新增/下线时池的懒加载与回收，避免重启。
6) 能提到可观测性：按站点打点，快速定位是哪个下游导致整体抖动。

**雷区**

1) 误以为全局单例 Client 就“线程不安全、不能复用”——实际上主流 Client 都是线程安全的，问题不在安全而在资源隔离和治理粒度。
2) 误以为连接池可以跨 host 复用连接——HTTP/1.1 不行，HTTP/2 也只是同一 origin 内多路复用，不能跨域名。
3) 只按域名分组却忽略端口、scheme、代理、TLS 配置差异，导致 key 冲突或复用错误配置。
4) 忘记给池设上限和淘汰，站点一多就内存/FD 泄漏。
5) 认为分组后就不用管并发上限，每个站点仍可能被自己的高并发打爆，需要配合限流。
6) 把“按站点分组”和“每次请求 new 一个 Client”混淆，后者会丢失连接复用，性能更差。

### 难度

★★☆

### 标签

`概念基础` `juejin`

---

## 8. 抽象类和接口的区别

> 原题 ID：`q3505` ｜ 原分类：概念基础 ｜ 来源：全平台面经采集(2026-09)·nowcoder

### 题干

抽象类和接口的区别

### 选项

（本题为问答题，原始题库无选项字段）

### 答案

抽象类表达“是什么”的继承关系，接口表达“能做什么”的能力契约；Java 中类单继承抽象类、可多实现接口，接口字段默认 public static final、方法默认 public abstract（Java 8 后有 default/static，Java 9 有 private）。

### 解析

抽象类和接口都是面向对象中用于抽象、解耦和多态的手段，但设计意图不同。

1. 语义与关系
- 抽象类：表示同一类事物的模板，强调 is-a。比如“动物”是抽象类，猫、狗继承它，共享 name、age 等状态和 eat() 等通用行为。
- 接口：表示一种能力或契约，强调 can-do / has-a。比如“会飞”是接口，鸟、飞机、超人都可以实现 Flyable，但它们并不属于同一继承体系。

2. 语法限制（以 Java 为例）
- 继承数量：类只能 extends 一个抽象类，但可以 implements 多个接口。
- 成员变量：抽象类可有普通字段、静态字段、各种访问修饰符；接口字段默认 public static final，即常量。
- 方法：抽象类可包含抽象方法和具体方法；接口在 Java 8 前只能有 public abstract 方法，Java 8 增加 default 和 static 方法，Java 9 增加 private 方法。
- 构造器：抽象类有构造器，供子类 super() 调用；接口没有构造器。
- 访问修饰符：抽象方法可 protected/public；接口方法默认 public。

3. 设计选择
- 需要复用代码、维护共享状态、定义模板流程时用抽象类，例如模板方法模式。
- 需要跨不同继承体系定义能力、实现多继承类型效果、面向接口编程时用接口，例如 Comparable、Runnable、Spring 的 Repository。
- 常见组合：抽象类实现接口，提供骨架实现，子类再继承抽象类，如 AbstractList 实现 List。

4. 通俗类比
抽象类像“员工入职模板”：有固定字段和流程，具体岗位继承后补充；接口像“会开车”证书：不管你是程序员还是销售，只要会开车就能拿到，且可以同时拥有多个证书。

**加分点**

1. Java 8 default 方法是为了接口演进而不破坏已有实现，例如 Collection 新增 stream()；但 default 方法不能访问实现类状态，且多接口 default 冲突时子类必须显式重写。
2. 接口不能有实例字段，因此无法直接实现状态共享；抽象类可以，但单继承限制了扩展。
3. 设计原则：优先组合/接口，而非继承；Effective Java 建议“接口优于抽象类”，但需要骨架实现时用抽象类。
4. 源码例子：AbstractList 实现 List 并提供 Itr 迭代器骨架；Java 集合框架大量使用接口 + 抽象类组合。
5. 其他语言差异：C++ 无接口关键字，用纯虚函数模拟；Go 接口是隐式实现，更彻底地面向能力。

**雷区**

1. 误以为接口完全不能有方法体：Java 8 后 default/static 方法可以有实现。
2. 误以为抽象类不能有构造器：抽象类有构造器，只是不能直接 new。
3. 误以为接口字段是实例变量：接口字段默认 public static final，是常量。
4. 把“抽象类单继承、接口多实现”当成唯一区别，忽略语义和设计意图。
5. 认为所有场景都该用接口，忽略需要共享状态和代码复用时抽象类更合适。
6. 混淆抽象类和接口在访问修饰符、方法默认修饰符上的差异。

### 难度

★★☆

### 标签

`概念基础` `nowcoder`

---
