/** @type {import("stylelint").Config} */
export default {
  extends: ['stylelint-config-standard'],
  rules: {
    'color-no-invalid-hex': true, // Запретит писать #fffz (несуществующие цвета)
    'declaration-block-no-duplicate-properties': true, // Запретит писать margin: 10px; margin: 20px; в одном блоке
    'block-no-empty': true, // Запретит оставлять пустые классы { }
    'selector-class-pattern': null // Отключаем принудительный kebab-case для классов (чтобы можно было писать BEM-классы с __)
  }
};
