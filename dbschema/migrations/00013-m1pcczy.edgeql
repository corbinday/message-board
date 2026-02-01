CREATE MIGRATION m1pcczyitadz5tgx5j4tn7244reprgnba44yfz7yvqok4yfbgzocmq
    ONTO m1mz5i5kvjgmfshfrjeh6fm34hrjjnuxfxoskt6ric5m7zirci4nvq
{
  ALTER TYPE default::PixelAnimation {
      ALTER PROPERTY frames {
          CREATE CONSTRAINT std::max_value(24);
          CREATE CONSTRAINT std::min_value(2);
      };
  };
};
