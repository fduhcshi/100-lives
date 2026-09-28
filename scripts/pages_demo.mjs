import { buildResult } from "../cloudflare/logic.js";

// Fictional, hand-written data for the public GitHub Pages showcase.
// It never comes from a visitor's form or a model API.
const request = {
  profile: "想在闲暇时间培养一项可以长期坚持的爱好。每周有一个下午可以投入，预算适中；希望享受创作过程，也愿意认识有共同兴趣的人。",
  choice_a: "每周参加陶艺课，练习手作",
  choice_b: "学习摄影，记录日常与自然",
  years: 3,
  num_lives: 6,
};

const scenarios = [
  {
    world: ["社区艺术中心开业，周末活动增多", "工作日节奏稳定", "课程和器材价格平稳", "朋友也开始寻找新爱好", "社区举办小型创作市集", "偶然看到一场免费手作展"],
    a: ["报名陶艺入门课", "在社区市集摆出第一批作品", "形成固定的每周手作习惯"],
    b: ["加入周末摄影散步", "拍摄社区文化节", "完成一组街区照片"],
    scores: [[68, 64, 75, 82, 18], [68, 63, 72, 78, 23]],
  },
  {
    world: ["生活开支增加，需要控制兴趣预算", "工作日安排变化不大", "材料与器材都略有涨价", "朋友更愿意参加低成本活动", "图书馆提供免费创作空间", "一次闲置物品交换会带来灵感"],
    a: ["先体验短期陶艺课", "改用共享工作室练习", "用有限预算继续手作"],
    b: ["用手机练习构图", "参加免费的摄影交流", "完成一组不依赖昂贵器材的作品"],
    scores: [[67, 58, 68, 70, 29], [67, 71, 72, 79, 20]],
  },
  {
    world: ["连续阴雨让室内活动更受欢迎", "工作日事务略有增加", "兴趣支出保持平稳", "周末聚会常改为室内活动", "手作空间延长开放时间", "一次雨天漫步发现新的拍摄角度"],
    a: ["在室内工作室开始练习", "尝试釉色与造型", "做出一套日常使用的杯盘"],
    b: ["练习雨天光线拍摄", "整理室内静物照片", "形成自己的照片主题"],
    scores: [[66, 63, 70, 80, 21], [66, 64, 67, 73, 28]],
  },
  {
    world: ["社区文化节向居民征集作品", "工作日留有稳定空闲", "展览和活动费用可控", "邻居开始组织共同创作", "可以参加一次公开展览", "临时认识一位耐心的指导者"],
    a: ["学习基础拉坯", "把作品送去社区展览", "与新朋友一起开设体验活动"],
    b: ["记录社区活动", "参加文化节照片征集", "办一场小型摄影分享"],
    scores: [[70, 61, 77, 83, 17], [70, 64, 81, 84, 16]],
  },
  {
    world: ["朋友邀请一起参加周末社群", "工作日节奏保持平稳", "团体活动费用小幅下降", "共同兴趣让联系更频繁", "社群举办主题创作活动", "一次临时邀约促成合作"],
    a: ["与朋友一起上陶艺课", "合作准备手作礼物", "保留每月一次的共同创作"],
    b: ["加入朋友的摄影小组", "一起完成主题拍摄", "持续记录社群的变化"],
    scores: [[65, 64, 76, 80, 20], [65, 62, 83, 85, 15]],
  },
  {
    world: ["周末可支配时间减少，兴趣需要更灵活的安排", "工作日偶尔延长", "短期课程和轻便设备更划算", "家人需要更多周末陪伴", "附近开放了随到随用的创作空间", "一次短途出游让人重新安排时间"],
    a: ["选择灵活预约的陶艺课", "在家完成小型手作", "把陶艺保留为偶尔的放松方式"],
    b: ["随手记录日常画面", "利用短途出游练习拍摄", "用轻量摄影保持创作习惯"],
    scores: [[66, 67, 69, 73, 27], [66, 70, 68, 76, 24]],
  },
];

const keys = ["macro_environment", "career_shock", "financial_shock", "relationship_shock", "opportunity", "random_event"];
const universes = scenarios.map((scenario, index) => ({
  id: index + 1,
  ...Object.fromEntries(keys.map((key, i) => [key, scenario.world[i]])),
}));

function trajectory(scenario, universe, choice) {
  const pottery = choice === "A";
  const events = scenario[pottery ? "a" : "b"];
  const [career, finance, relationship, wellbeing, regret] = scenario.scores[pottery ? 0 : 1];
  const activity = pottery ? "陶艺" : "摄影";
  const place = pottery ? "本地陶艺工作室" : "附近街区与公园";
  const budget = pottery ? "课程与材料" : "器材与出行";
  const community = pottery ? "手作同学" : "摄影伙伴";
  const years = events.map((event, index) => ({
    year: index + 1,
    career: "保持日常安排，为兴趣留出固定时间",
    finance: `控制${budget}支出，在预算内继续尝试`,
    relationship: `与${community}交流，也保留陪伴亲友的时间`,
    location: place,
    wellbeing: index === 0 ? `开始练习${activity}，享受专注的过程` : `逐渐找到适合自己的${activity}节奏`,
    major_event: event,
    decision: index === 2 ? `决定以适合自己的频率继续${activity}` : `继续投入时间学习${activity}`,
  }));
  return {
    id: `${choice.toLowerCase()}_u${String(universe.id).padStart(2, "0")}`,
    universe_id: universe.id,
    choice,
    summary: `${events[0]}，随后${events[1]}；第三年${events[2]}。这条路的收获与限制都取决于时间和预算。`,
    years,
    features: {
      career_direction: "flat", financial_direction: finance >= 67 ? "flat" : "down",
      wellbeing_direction: wellbeing >= 78 ? "up" : "flat", location_change: false,
      startup: false, job_switch: false, relationship_change: relationship >= 75,
      main_theme: pottery ? "手作与专注" : "观察与记录",
    },
    final_career_score: career,
    final_finance_score: finance,
    final_relationship_score: relationship,
    final_wellbeing_score: wellbeing,
    regret_score: regret,
    critic: null,
    regenerated: 0,
    cluster_name: pottery ? "手作与专注" : "观察与记录",
  };
}

const trajectories = universes.flatMap((universe, index) => [
  trajectory(scenarios[index], universe, "A"),
  trajectory(scenarios[index], universe, "B"),
]);

const insight = {
  structural_difference: "陶艺更依赖固定的工作室与练习时间；摄影更容易利用零散时间，但也可能带来器材和出行花费。",
  deciding_factors: "每周可投入的时间、预算，以及更喜欢触摸材料还是观察画面，会影响体验。",
  unimportant_factors: "这组示例里，职业发展差异很小；不必为了一个模拟分数决定兴趣。",
  who_fits_a: "喜欢动手制作、愿意反复练习同一项手艺的人，可以试试陶艺。",
  who_fits_b: "喜欢外出观察、记录日常，也希望安排更灵活的人，可以试试摄影。",
  biggest_risk: "把短暂的新鲜感当作长期习惯，或一次投入太多预算。",
  info_to_confirm: "先体验一节课程和一次拍摄活动，再判断哪种过程更想继续。",
};

function cluster(name, description, ids) {
  return {
    name, description, trajectory_ids: ids,
    common_pattern: description,
    key_risk: "时间和预算不足时，练习容易中断。",
    key_opportunity: "找到同好和适合自己的固定节奏。",
    representative_trajectory_id: ids[0],
  };
}

export function createPagesDemo() {
  const result = buildResult("pages-demo", request, universes, trajectories, insight, 0, 0);
  result.disclaimer = "这是一份手工编写的虚构示例，仅展示报告界面与交互；分数不代表现实概率，也不是对未来的预测。";
  result.choice_summaries.A.common_risks = ["固定课程和材料费用可能影响持续性。"];
  result.choice_summaries.A.common_opportunities = ["在工作室结识同好，逐渐形成手作习惯。"];
  result.choice_summaries.A.clusters = [
    cluster("稳定练习", "在固定时间里持续做出作品。", ["a_u01", "a_u03", "a_u04"]),
    cluster("灵活尝试", "根据预算与空闲时间调整练习强度。", ["a_u02", "a_u05", "a_u06"]),
  ];
  result.choice_summaries.B.common_risks = ["器材花费与外出安排可能超过预期。"];
  result.choice_summaries.B.common_opportunities = ["把日常观察变成可分享的照片记录。"];
  result.choice_summaries.B.clusters = [
    cluster("主题创作", "围绕社区与自然形成自己的拍摄主题。", ["b_u01", "b_u03", "b_u04"]),
    cluster("轻量记录", "用手机或轻便设备保持观察习惯。", ["b_u02", "b_u05", "b_u06"]),
  ];
  result.matched_comparison.divergence_insight = "同样的外部条件下，两种爱好的差别更多体现在时间安排、花费和社交方式。";
  return result;
}
