CREATE MIGRATION m12ynowoyhkjkuvafbhnfxvlntmr66lqiijpio2dbpacfrbtdrn6oa
    ONTO m1eh26dmn5yviqxkgmbcsrhlsi3wqqmnn7s5euxdxa5hvivuqllqfq
{
  ALTER TYPE default::Board {
      CREATE PROPERTY last_connected_at: std::datetime;
  };
};
